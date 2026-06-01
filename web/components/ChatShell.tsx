"use client";

import { useCallback, useRef, useState } from "react";
import type { ChatMessage, CompletePayload, ProgressEvent, RunOptions } from "@/lib/types";
import { streamChat } from "@/lib/api";
import AgentActivity from "./AgentActivity";
import Composer from "./Composer";
import FinalAnswer from "./FinalAnswer";
import MessageList from "./MessageList";

const DEFAULT_OPTIONS: RunOptions = {
  fast_mode: false,
  no_search: false,
  max_hits: 6,
};

type PanelState =
  | { type: "idle" }
  | { type: "running"; events: ProgressEvent[] }
  | { type: "done"; result: CompletePayload; events: ProgressEvent[] };

export default function ChatShell() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [streamingText, setStreamingText] = useState<string | undefined>();
  const [panel, setPanel] = useState<PanelState>({ type: "idle" });
  const [options, setOptions] = useState<RunOptions>(DEFAULT_OPTIONS);
  const [showRaw, setShowRaw] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  // Ref tracks running state so callbacks don't close over stale booleans.
  const runningRef = useRef(false);

  const running = panel.type === "running";

  const handleSubmit = useCallback(
    async (message: string) => {
      // Use ref, not the closed-over `running` derived value, to prevent
      // double-submission when the callback is called before React re-renders.
      if (runningRef.current) return;
      runningRef.current = true;

      setMessages((prev) => [...prev, { role: "user", content: message }]);
      setStreamingText("Understanding your question…");
      setPanel({ type: "running", events: [] });

      abortRef.current = new AbortController();

      try {
        await streamChat(
          message,
          options,
          {
            onProgress(event) {
              setPanel((prev) => {
                if (prev.type !== "running") return prev;
                return { type: "running", events: [...prev.events, event] };
              });
              setStreamingText(event.label + "…");
            },
            onComplete(payload) {
              runningRef.current = false;
              setMessages((prev) => [
                ...prev,
                { role: "assistant", content: payload.answer, result: payload },
              ]);
              setStreamingText(undefined);
              setPanel((prev) => ({
                type: "done",
                result: payload,
                events: prev.type === "running" ? prev.events : [],
              }));
            },
            onError(msg) {
              runningRef.current = false;
              setMessages((prev) => [
                ...prev,
                { role: "assistant", content: `Error: ${msg}` },
              ]);
              setStreamingText(undefined);
              setPanel({ type: "idle" });
            },
          },
          abortRef.current.signal
        );
      } catch (e) {
        runningRef.current = false;
        if ((e as Error).name !== "AbortError") {
          setMessages((prev) => [
            ...prev,
            { role: "assistant", content: "Connection error." },
          ]);
        }
        // Always reset panel on any thrown error (including AbortError from Clear).
        setPanel({ type: "idle" });
        setStreamingText(undefined);
      }
    },
    [options] // `running` removed — guarded by runningRef instead
  );

  function handleClear() {
    abortRef.current?.abort();
    runningRef.current = false;
    setMessages([]);
    setStreamingText(undefined);
    setPanel({ type: "idle" });
  }

  const lastResult =
    panel.type === "done"
      ? panel.result
      : messages.findLast((m) => m.role === "assistant" && m.result)?.result;

  const panelEvents =
    panel.type === "running" || panel.type === "done" ? panel.events : [];

  return (
    <div className="flex h-screen bg-bg text-text overflow-hidden">
      {/* Left: chat */}
      <div className="flex flex-col flex-1 min-w-0 border-r border-border">
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
              onChange={(e) => setShowRaw(e.target.checked)}
              className="accent-accent"
            />
            Raw trace
          </label>
        </div>

        {/* Messages */}
        <MessageList messages={messages} streamingContent={streamingText} />

        {/* Composer */}
        <Composer
          options={options}
          onOptionsChange={setOptions}
          onSubmit={handleSubmit}
          onClear={handleClear}
          disabled={running}
        />
      </div>

      {/* Right: answer support */}
      <div className="w-80 xl:w-96 flex flex-col flex-shrink-0 overflow-y-auto p-4 gap-3">
        <div className="text-xs font-semibold uppercase tracking-widest text-muted px-1 pt-1">
          Answer Support
        </div>

        {panel.type === "running" && (
          <AgentActivity events={panelEvents} running={true} />
        )}

        {panel.type === "done" && panelEvents.length > 0 && (
          <AgentActivity events={panelEvents} running={false} />
        )}

        {lastResult && (
          <FinalAnswer result={lastResult} showRaw={showRaw} />
        )}

        {panel.type === "idle" && messages.length === 0 && (
          <div className="text-xs text-muted/50 px-1">
            Ask a question to see the reasoning trace.
          </div>
        )}
      </div>
    </div>
  );
}
