"use client";

import { useEffect, useRef } from "react";
import type { ChatMessage } from "@/lib/types";

interface Props {
  messages: ChatMessage[];
  streamingContent?: string;
}

export default function MessageList({ messages, streamingContent }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamingContent]);

  if (messages.length === 0 && !streamingContent) {
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
      {messages.map((msg, i) => (
        <div
          key={i}
          className={`flex ${
            msg.role === "user" ? "justify-end" : "justify-start"
          }`}
        >
          <div
            className={`max-w-[85%] rounded-2xl px-4 py-3 text-sm leading-relaxed ${
              msg.role === "user"
                ? "bg-accent/15 text-text rounded-br-sm"
                : "bg-surface border border-border text-text/90 rounded-bl-sm"
            }`}
          >
            {msg.content}
          </div>
        </div>
      ))}
      {streamingContent && (
        <div className="flex justify-start">
          <div className="max-w-[85%] rounded-2xl rounded-bl-sm px-4 py-3 text-sm leading-relaxed bg-surface border border-border text-text/90">
            {streamingContent}
            <span className="inline-block w-1.5 h-3.5 bg-accent/70 ml-0.5 animate-pulse align-text-bottom" />
          </div>
        </div>
      )}
      <div ref={bottomRef} />
    </div>
  );
}
