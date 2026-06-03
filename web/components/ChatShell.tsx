"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { PanelRightClose, PanelRightOpen } from "lucide-react";
import type {
  AssistantMessage,
  ChatMessage,
  ChatSession,
  CompletePayload,
  HistoryEntry,
  ProgressEvent,
  RunOptions,
  SelectedStage,
} from "@/lib/types";
import { isAssistant, isUser } from "@/lib/types";
import { streamChat } from "@/lib/api";
import { createChatTitle, loadChats, saveChats } from "@/lib/storage";
import Composer, { type ComposerHandle } from "./Composer";
import Inspector from "./Inspector";
import MessageList from "./MessageList";
import Sidebar from "./Sidebar";

// ── Landing hero suggestions ──────────────────────────────────────────────────

const SUGGESTIONS = [
  {
    category: "Explain an event",
    example: "What happened with the 2023 debt ceiling negotiations?",
  },
  {
    category: "Compare perspectives",
    example: "What were the key positions of both parties on the 2023 debt ceiling?",
  },
  {
    category: "Audit a claim",
    example: "Is it accurate that the Supreme Court ruled affirmative action unconstitutional?",
  },
];

// ── Helpers ───────────────────────────────────────────────────────────────────

function generateId(): string {
  return Date.now().toString(36) + Math.random().toString(36).slice(2);
}

const DEFAULT_OPTIONS: RunOptions = {
  fast_mode: false,
  no_search: false,
  max_hits: 6,
};

// ── Bounded history builder ───────────────────────────────────────────────────
// Sends at most the last 6 completed messages (~3 pairs) to the backend.
// User messages are truncated to 500 chars; assistant answers to 1000 chars.
// Running/error assistant messages are excluded.

const USER_TRUNC = 500;
const ASSISTANT_TRUNC = 1000;
const MAX_HISTORY_ENTRIES = 6;

function buildBoundedHistory(messages: ChatMessage[]): HistoryEntry[] {
  const eligible: HistoryEntry[] = [];
  for (const m of messages) {
    if (isUser(m)) {
      eligible.push({ role: "user", content: m.content.slice(0, USER_TRUNC) });
    } else if (isAssistant(m) && m.status === "done" && m.result) {
      eligible.push({ role: "assistant", content: m.result.answer.slice(0, ASSISTANT_TRUNC) });
    }
  }
  return eligible.slice(-MAX_HISTORY_ENTRIES);
}

// ── Component ─────────────────────────────────────────────────────────────────

export default function ChatShell() {
  // ── Persistent sessions ───────────────────────────────────────────────────
  const [chats, setChats] = useState<ChatSession[]>([]);
  const [activeChatId, setActiveChatId] = useState<string | null>(null);
  const [storageReady, setStorageReady] = useState(false);

  // ── Layout ────────────────────────────────────────────────────────────────
  const [leftOpen, setLeftOpen] = useState(true);
  const [rightOpen, setRightOpen] = useState(true);

  // ── UI state ──────────────────────────────────────────────────────────────
  const [options, setOptions] = useState<RunOptions>(DEFAULT_OPTIONS);
  const [showRaw, setShowRaw] = useState(false);
  const [selected, setSelected] = useState<SelectedStage | null>(null);
  const [autoFollow, setAutoFollow] = useState(true);

  // ── Refs (survive async callbacks without stale-closure risk) ─────────────
  const activeIdRef = useRef<string | null>(null);      // active assistant msg ID
  const activeChatIdRef = useRef<string | null>(null);  // active session ID
  const runningRef = useRef(false);
  const abortRef = useRef<AbortController | null>(null);
  const composerRef = useRef<ComposerHandle>(null);
  const messagesRef = useRef<ChatMessage[]>([]);         // snapshot for history building

  // ── Load from localStorage on mount ──────────────────────────────────────
  useEffect(() => {
    setChats(loadChats());
    setStorageReady(true);
  }, []);

  // ── Debounced localStorage save ───────────────────────────────────────────
  useEffect(() => {
    if (!storageReady) return;
    const id = setTimeout(() => saveChats(chats), 600);
    return () => clearTimeout(id);
  }, [chats, storageReady]);

  // ── Derived state ─────────────────────────────────────────────────────────
  const activeChat = chats.find(c => c.id === activeChatId) ?? null;
  const messages: ChatMessage[] = activeChat?.messages ?? [];
  const hasMessages = messages.length > 0;
  // Keep ref current so handleSubmit can build history without a stale closure.
  messagesRef.current = messages;
  const running = messages.some(m => isAssistant(m) && m.status === "running");

  // ── Inspector auto-follow ─────────────────────────────────────────────────
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

  // ── Session management ────────────────────────────────────────────────────

  function handleNewChat() {
    if (runningRef.current) {
      abortRef.current?.abort();
      runningRef.current = false;
      activeIdRef.current = null;
    }
    activeChatIdRef.current = null;
    setActiveChatId(null);
    setSelected(null);
    setAutoFollow(true);
  }

  function handleSelectChat(id: string) {
    if (runningRef.current) return;
    activeChatIdRef.current = id;
    setActiveChatId(id);
    setSelected(null);
    setAutoFollow(true);
  }

  function handleDeleteChat(id: string) {
    if (activeChatId === id) {
      const remaining = chats.filter(c => c.id !== id);
      const nextId = remaining[0]?.id ?? null;
      activeChatIdRef.current = nextId;
      setActiveChatId(nextId);
      setSelected(null);
    }
    setChats(prev => prev.filter(c => c.id !== id));
  }

  // ── Submit handler ────────────────────────────────────────────────────────

  const handleSubmit = useCallback(
    async (message: string) => {
      if (runningRef.current) return;
      runningRef.current = true;

      setAutoFollow(true);
      setSelected(null);

      // Find or create the active session
      let chatId = activeChatIdRef.current;
      const isNewSession = !chatId;

      const userMsgId = generateId();
      const assistantMsgId = generateId();
      activeIdRef.current = assistantMsgId;

      const userMsg: ChatMessage = { id: userMsgId, role: "user", content: message };
      const assistantMsg: ChatMessage = {
        id: assistantMsgId,
        role: "assistant",
        status: "running",
        traceEvents: [],
      };

      if (isNewSession) {
        chatId = generateId();
        activeChatIdRef.current = chatId;
        setActiveChatId(chatId);
        const newSession: ChatSession = {
          id: chatId,
          title: createChatTitle(message),
          createdAt: Date.now(),
          updatedAt: Date.now(),
          messages: [userMsg, assistantMsg],
        };
        setChats(prev => [newSession, ...prev]);
      } else {
        setChats(prev =>
          prev.map(c =>
            c.id !== chatId
              ? c
              : { ...c, updatedAt: Date.now(), messages: [...c.messages, userMsg, assistantMsg] }
          )
        );
      }

      const thisChatId = chatId!;
      abortRef.current = new AbortController();

      // Build bounded history from completed turns BEFORE the current one.
      // messagesRef.current reflects the state at render time (before new messages
      // were appended), so it contains only prior turns.
      const history = buildBoundedHistory(messagesRef.current);

      try {
        await streamChat(
          message,
          options,
          {
            onProgress(event: ProgressEvent) {
              const msgId = activeIdRef.current;
              if (!msgId) return;
              setChats(prev =>
                prev.map(c => {
                  if (c.id !== thisChatId) return c;
                  return {
                    ...c,
                    messages: c.messages.map(m => {
                      if (m.id !== msgId || !isAssistant(m)) return m;
                      return { ...m, traceEvents: [...m.traceEvents, event] };
                    }),
                  };
                })
              );
            },

            onStageNote(stageId: string, text: string) {
              const msgId = activeIdRef.current;
              if (!msgId) return;
              setChats(prev =>
                prev.map(c => {
                  if (c.id !== thisChatId) return c;
                  return {
                    ...c,
                    messages: c.messages.map(m => {
                      if (m.id !== msgId || !isAssistant(m)) return m;
                      const prevHistory = m.liveNoteHistory?.[stageId] ?? [];
                      const lastNote = prevHistory[prevHistory.length - 1];
                      const newHistory = lastNote === text
                        ? prevHistory
                        : [...prevHistory, text].slice(-4);
                      return {
                        ...m,
                        liveNotes: { ...(m.liveNotes ?? {}), [stageId]: text },
                        liveNoteHistory: { ...(m.liveNoteHistory ?? {}), [stageId]: newHistory },
                      };
                    }),
                  };
                })
              );
            },

            onComplete(payload: CompletePayload) {
              runningRef.current = false;
              const msgId = activeIdRef.current;
              activeIdRef.current = null;
              if (!msgId) return;
              setChats(prev =>
                prev.map(c => {
                  if (c.id !== thisChatId) return c;
                  return {
                    ...c,
                    updatedAt: Date.now(),
                    messages: c.messages.map(m => {
                      if (m.id !== msgId || !isAssistant(m)) return m;
                      return { ...m, status: "done" as const, result: payload };
                    }),
                  };
                })
              );
            },

            onError(msg: string) {
              runningRef.current = false;
              const msgId = activeIdRef.current;
              activeIdRef.current = null;
              if (!msgId) return;
              setChats(prev =>
                prev.map(c => {
                  if (c.id !== thisChatId) return c;
                  return {
                    ...c,
                    updatedAt: Date.now(),
                    messages: c.messages.map(m => {
                      if (m.id !== msgId || !isAssistant(m)) return m;
                      return { ...m, status: "error" as const, error: msg };
                    }),
                  };
                })
              );
            },
          },
          abortRef.current.signal,
          history
        );
      } catch (e) {
        runningRef.current = false;
        const msgId = activeIdRef.current;
        activeIdRef.current = null;
        const isAbort = (e as Error).name === "AbortError";
        if (msgId) {
          setChats(prev =>
            prev.map(c => {
              if (c.id !== thisChatId) return c;
              return {
                ...c,
                updatedAt: Date.now(),
                messages: c.messages.map(m => {
                  if (m.id !== msgId || !isAssistant(m)) return m;
                  return {
                    ...m,
                    status: "error" as const,
                    error: isAbort ? "Cancelled." : "Connection error.",
                  };
                }),
              };
            })
          );
        }
      }
    },
    [options]
  );

  // ── Interaction handlers ──────────────────────────────────────────────────

  function handleFollowUp(text: string) {
    composerRef.current?.setValue(text);
  }

  function handleSelectStage(messageId: string, stageId: string) {
    setAutoFollow(false);
    setSelected(prev =>
      prev?.messageId === messageId && prev.stageId === stageId
        ? null
        : { messageId, stageId }
    );
    if (!rightOpen) setRightOpen(true);
  }

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div className="flex h-screen bg-bg text-text overflow-hidden">

      {/* ── Left Sidebar ── */}
      <Sidebar
        chats={chats}
        activeChatId={activeChatId}
        open={leftOpen}
        onToggle={() => setLeftOpen(o => !o)}
        onNewChat={handleNewChat}
        onSelectChat={handleSelectChat}
        onDeleteChat={handleDeleteChat}
      />

      {/* ── Main Chat Area ── */}
      <div className="flex flex-col flex-1 min-w-0 overflow-hidden">

        {/* Header */}
        <div className="px-4 py-3 border-b border-border flex items-center gap-3 flex-shrink-0 min-w-0">
          <p className="flex-1 text-xs text-muted/55 truncate min-w-0">
            {activeChat?.title ?? "Revere — Political Events AI"}
          </p>
          <label className="flex items-center gap-1.5 text-xs text-muted/45 cursor-pointer select-none flex-shrink-0">
            <input
              type="checkbox"
              checked={showRaw}
              onChange={e => setShowRaw(e.target.checked)}
              className="accent-accent"
            />
            Raw
          </label>
          <button
            type="button"
            onClick={() => setRightOpen(o => !o)}
            className="p-1.5 rounded-md text-muted/45 hover:text-text hover:bg-border/40 transition-colors flex-shrink-0"
            aria-label={rightOpen ? "Collapse inspector" : "Expand inspector"}
          >
            {rightOpen ? <PanelRightClose size={14} /> : <PanelRightOpen size={14} />}
          </button>
        </div>

        {/* Content: landing hero or active chat */}
        {hasMessages ? (
          <>
            <MessageList
              key={activeChatId ?? "landing"}
              messages={messages}
              selected={effectiveSelected}
              onSelectStage={handleSelectStage}
              onFollowUp={handleFollowUp}
              showRaw={showRaw}
            />
            <Composer
              ref={composerRef}
              options={options}
              onOptionsChange={setOptions}
              onSubmit={handleSubmit}
              onClear={handleNewChat}
              clearLabel="New"
              disabled={running}
              variant="dock"
            />
          </>
        ) : (
          <div className="flex-1 flex flex-col items-center justify-center px-6 py-10 overflow-y-auto">
            <div className="w-full max-w-xl space-y-7">
              {/* Hero title */}
              <div className="text-center space-y-2.5">
                <h1 className="text-2xl font-serif text-text/85 tracking-tight leading-snug">
                  What political event should we unpack?
                </h1>
                <p className="text-sm text-muted/55 max-w-sm mx-auto leading-relaxed">
                  Ask for a balanced explanation, source audit, or perspective map.
                  Reasoning is fully transparent.
                </p>
              </div>

              {/* Hero Composer */}
              <Composer
                ref={composerRef}
                options={options}
                onOptionsChange={setOptions}
                onSubmit={handleSubmit}
                disabled={running}
                variant="hero"
              />

              {/* Suggestion cards */}
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5">
                {SUGGESTIONS.map((s, i) => (
                  <button
                    key={i}
                    type="button"
                    onClick={() => composerRef.current?.setValue(s.example)}
                    className="text-left rounded-xl border border-border/45 bg-surface/50 px-3.5 py-3 hover:bg-surface hover:border-border/70 transition-colors group"
                  >
                    <p className="text-[10px] font-medium text-muted/50 uppercase tracking-wider mb-1.5">
                      {s.category}
                    </p>
                    <p className="text-[12px] text-text/50 leading-relaxed group-hover:text-text/65 transition-colors">
                      {s.example}
                    </p>
                  </button>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>

      {/* ── Right Inspector ── */}
      <div
        className={`flex-shrink-0 border-l border-border flex flex-col overflow-hidden ${
          rightOpen ? "w-80" : "w-12"
        }`}
      >
        {rightOpen ? (
          <Inspector selected={effectiveSelected} messages={messages} />
        ) : (
          <div className="flex flex-col items-center pt-3 gap-3">
            <button
              type="button"
              onClick={() => setRightOpen(true)}
              className="p-2 text-muted/45 hover:text-text rounded-md hover:bg-border/30 transition-colors"
              aria-label="Open inspector"
            >
              <PanelRightOpen size={14} />
            </button>
            <span
              className="text-[9px] text-muted/25 uppercase tracking-widest select-none"
              style={{ writingMode: "vertical-rl" }}
            >
              Inspector
            </span>
          </div>
        )}
      </div>

    </div>
  );
}
