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
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
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
    <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
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
            <div key={msg.id} className="w-full">
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
