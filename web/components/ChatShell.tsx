"use client";

import { useCallback, useMemo, useRef, useState } from "react";
import type {
  AssistantMessage,
  ChatMessage,
  CompletePayload,
  ProgressEvent,
  RunOptions,
  SelectedStage,
} from "@/lib/types";
import { isAssistant } from "@/lib/types";
import { streamChat } from "@/lib/api";
import Composer, { type ComposerHandle } from "./Composer";
import Inspector from "./Inspector";
import MessageList from "./MessageList";

function generateId(): string {
  return Date.now().toString(36) + Math.random().toString(36).slice(2);
}

const DEFAULT_OPTIONS: RunOptions = {
  fast_mode: false,
  no_search: false,
  max_hits: 6,
};

export default function ChatShell() {
  // Messages are the single source of truth.
  // The active assistant message lives inside this array with status="running".
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [options, setOptions] = useState<RunOptions>(DEFAULT_OPTIONS);
  const [showRaw, setShowRaw] = useState(false);
  const [selected, setSelected] = useState<SelectedStage | null>(null);
  const [autoFollow, setAutoFollow] = useState(true);

  // Refs that survive async callbacks without stale-closure risk.
  const activeIdRef = useRef<string | null>(null);
  const runningRef = useRef(false);
  const abortRef = useRef<AbortController | null>(null);
  const composerRef = useRef<ComposerHandle>(null);

  // Derived from messages state — correct for UI rendering.
  const running = messages.some(m => isAssistant(m) && m.status === "running");

  // Auto-follow: while running and no manual selection, inspector tracks the active stage.
  const autoSelectedStage = useMemo<SelectedStage | null>(() => {
    if (!autoFollow) return null;
    const runningMsg = messages.find(
      m => isAssistant(m) && m.status === "running"
    ) as AssistantMessage | undefined;
    if (!runningMsg) return null;
    const completedIds = new Set(
      runningMsg.traceEvents.filter(e => e.status === "completed").map(e => e.stage_id)
    );
    const lastStarted = [...runningMsg.traceEvents].reverse().find(e => e.status === "started");
    if (!lastStarted || completedIds.has(lastStarted.stage_id)) return null;
    return { messageId: runningMsg.id, stageId: lastStarted.stage_id };
  }, [autoFollow, messages]);

  const effectiveSelected = selected ?? autoSelectedStage;

  // ── Helpers for mutating the active assistant message ────────────────────

  function patchActive(
    id: string,
    patch: Partial<Omit<AssistantMessage, "id" | "role">>
  ) {
    setMessages(prev =>
      prev.map(m => {
        if (m.id !== id || !isAssistant(m)) return m;
        return { ...m, ...patch };
      })
    );
  }

  // ── Submit handler ────────────────────────────────────────────────────────

  const handleSubmit = useCallback(
    async (message: string) => {
      // Guard with ref, not stale `running` boolean, to prevent double-submit.
      if (runningRef.current) return;
      runningRef.current = true;

      setAutoFollow(true);
      setSelected(null);

      const userId = generateId();
      const assistantId = generateId();
      activeIdRef.current = assistantId;

      const userMsg: ChatMessage = {
        id: userId,
        role: "user",
        content: message,
      };
      const assistantMsg: ChatMessage = {
        id: assistantId,
        role: "assistant",
        status: "running",
        traceEvents: [],
      };

      setMessages(prev => [...prev, userMsg, assistantMsg]);

      abortRef.current = new AbortController();

      try {
        await streamChat(
          message,
          options,
          {
            onStart() {
              // Assistant message already created with status="running" — no-op.
            },

            onProgress(event: ProgressEvent) {
              const id = activeIdRef.current;
              if (!id) return;
              setMessages(prev =>
                prev.map(m => {
                  if (m.id !== id || !isAssistant(m)) return m;
                  return { ...m, traceEvents: [...m.traceEvents, event] };
                })
              );
            },

            onComplete(payload: CompletePayload) {
              runningRef.current = false;
              const id = activeIdRef.current;
              activeIdRef.current = null;
              if (!id) return;
              setMessages(prev =>
                prev.map(m => {
                  if (m.id !== id || !isAssistant(m)) return m;
                  return { ...m, status: "done", result: payload };
                })
              );
            },

            onError(msg: string) {
              runningRef.current = false;
              const id = activeIdRef.current;
              activeIdRef.current = null;
              if (!id) return;
              setMessages(prev =>
                prev.map(m => {
                  if (m.id !== id || !isAssistant(m)) return m;
                  return { ...m, status: "error", error: msg };
                })
              );
            },
          },
          abortRef.current.signal
        );
      } catch (e) {
        runningRef.current = false;
        const id = activeIdRef.current;
        activeIdRef.current = null;

        const isAbort = (e as Error).name === "AbortError";
        if (id) {
          setMessages(prev =>
            prev.map(m => {
              if (m.id !== id || !isAssistant(m)) return m;
              return {
                ...m,
                status: "error",
                error: isAbort ? "Cancelled." : "Connection error.",
              };
            })
          );
        }
      }
    },
    [options] // options captured at submit time — correct
  );

  // ── Clear ─────────────────────────────────────────────────────────────────

  function handleClear() {
    abortRef.current?.abort();
    runningRef.current = false;
    activeIdRef.current = null;
    setMessages([]);
    setSelected(null);
    setAutoFollow(true);
  }

  // ── Follow-up clicks ─────────────────────────────────────────────────────

  function handleFollowUp(text: string) {
    composerRef.current?.setValue(text);
  }

  // ── Inspector selection ───────────────────────────────────────────────────

  function handleSelectStage(messageId: string, stageId: string) {
    setAutoFollow(false);
    setSelected(prev =>
      prev?.messageId === messageId && prev.stageId === stageId
        ? null  // clicking same row toggles inspector off
        : { messageId, stageId }
    );
  }

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div className="flex h-screen bg-bg text-text overflow-hidden">
      {/* ── Chat column ── */}
      <div className="flex flex-col flex-1 min-w-0">
        {/* Header */}
        <div className="px-6 py-4 border-b border-border flex items-center justify-between flex-shrink-0">
          <div>
            <h1 className="text-base font-semibold text-text">Revere</h1>
            <p className="text-xs text-muted mt-0.5">
              Political events · Structured reasoning
            </p>
          </div>
          <label className="flex items-center gap-2 text-xs text-muted cursor-pointer select-none">
            <input
              type="checkbox"
              checked={showRaw}
              onChange={e => setShowRaw(e.target.checked)}
              className="accent-accent"
            />
            Raw trace
          </label>
        </div>

        {/* Message stream */}
        <MessageList
          messages={messages}
          selected={effectiveSelected}
          onSelectStage={handleSelectStage}
          onFollowUp={handleFollowUp}
          showRaw={showRaw}
        />

        {/* Composer */}
        <Composer
          ref={composerRef}
          options={options}
          onOptionsChange={setOptions}
          onSubmit={handleSubmit}
          onClear={handleClear}
          disabled={running}
        />
      </div>

      {/* ── Right inspector ── */}
      <div className="w-64 xl:w-72 flex-shrink-0 border-l border-border flex flex-col overflow-hidden">
        <div className="px-4 py-4 border-b border-border flex-shrink-0">
          <p className="text-xs font-semibold uppercase tracking-widest text-muted">
            Inspector
          </p>
        </div>
        <Inspector selected={effectiveSelected} messages={messages} />
      </div>
    </div>
  );
}
