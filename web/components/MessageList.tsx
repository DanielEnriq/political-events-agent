"use client";

import { useEffect, useRef } from "react";
import type { ChatMessage } from "@/lib/types";
import { isAssistant, isUser } from "@/lib/types";
import AssistantMessageView from "./AssistantMessage";

interface Props {
  messages: ChatMessage[];
  selected: { messageId: string; stageId: string } | null;
  onSelectStage: (messageId: string, stageId: string) => void;
  onFollowUp: (text: string) => void;
  showRaw: boolean;
}

export default function MessageList({
  messages,
  selected,
  onSelectStage,
  onFollowUp,
  showRaw,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const isAtBottomRef = useRef(true);
  const prevRunningIdRef = useRef<string | null>(null);
  const runningMsgRef = useRef<HTMLDivElement | null>(null);

  function onScroll() {
    const el = containerRef.current;
    if (!el) return;
    isAtBottomRef.current =
      el.scrollHeight - el.scrollTop - el.clientHeight < 100;
  }

  useEffect(() => {
    const runningMsg = messages.find(m => isAssistant(m) && m.status === "running");
    const currentRunningId = runningMsg?.id ?? null;
    const prevRunningId = prevRunningIdRef.current;
    prevRunningIdRef.current = currentRunningId;

    // New follow-up turn started — always scroll to the new running message
    // regardless of scroll position (user may have scrolled up to read a prior answer).
    if (currentRunningId !== null && currentRunningId !== prevRunningId) {
      requestAnimationFrame(() => {
        runningMsgRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
      });
      return;
    }

    // On completion (running → done), don't jump to bottom — let answer reveal in place.
    if (prevRunningId !== null && currentRunningId === null) return;

    // During an ongoing run, auto-scroll only if near the bottom.
    if (isAtBottomRef.current) {
      bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [messages]);

  if (messages.length === 0) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center text-center px-4">
        <p className="text-muted text-sm leading-relaxed max-w-sm">
          Ask about US political events, candidates,
          <br />
          legislation, or court decisions.
        </p>
        <p className="text-muted/50 text-xs mt-2">
          Structured reasoning with auditable source trace.
        </p>
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      onScroll={onScroll}
      className="flex-1 overflow-y-auto px-4 py-4 space-y-4"
    >
      {messages.map(msg => {
        if (isUser(msg)) {
          return (
            <div key={msg.id} className="flex justify-end">
              <div className="max-w-[85%] rounded-2xl rounded-br-sm px-4 py-3 text-sm leading-relaxed bg-accent/15 text-text">
                {msg.content}
              </div>
            </div>
          );
        }

        if (isAssistant(msg)) {
          return (
            <div
              key={msg.id}
              className="w-full"
              ref={msg.status === "running" ? runningMsgRef : undefined}
            >
              <AssistantMessageView
                message={msg}
                selectedStageId={
                  selected?.messageId === msg.id ? selected.stageId : undefined
                }
                onSelectStage={stageId => onSelectStage(msg.id, stageId)}
                onFollowUp={onFollowUp}
                showRaw={showRaw}
              />
            </div>
          );
        }

        return null;
      })}
      <div ref={bottomRef} />
    </div>
  );
}
