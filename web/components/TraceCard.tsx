"use client";

import { useEffect, useRef, useState } from "react";
import type { AuditMicroEvent, AssistantMessage, MicroEventKind, ProgressEvent } from "@/lib/types";

function dedupeByStage(events: ProgressEvent[]): ProgressEvent[] {
  const latest = new Map<string, ProgressEvent>();
  for (const e of events) {
    const prev = latest.get(e.stage_id);
    if (!prev || e.status === "completed") {
      latest.set(e.stage_id, e);
    }
  }
  const seen = new Set<string>();
  const out: ProgressEvent[] = [];
  for (const e of events) {
    if (!seen.has(e.stage_id)) {
      seen.add(e.stage_id);
      out.push(latest.get(e.stage_id)!);
    }
  }
  return out;
}

function formatDuration(ms: number): string {
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${ms}ms`;
}

function microEventColor(kind?: MicroEventKind): string {
  switch (kind) {
    case "warning":      return "text-yellow-500/60";
    case "source":       return "text-muted/55";
    case "perspective":  return "text-accent/55";
    case "verification": return "text-green-400/55";
    case "neutrality":   return "text-accent/60";
    default:             return "text-muted/50";
  }
}

function parseMicroEvent(me: AuditMicroEvent): { label: string | null; content: string } {
  const text = me.text;
  const patterns: [RegExp, string][] = [
    [/^Normalized to: (.+)$/, "Normalized query"],
    [/^Intent classified as (.+)$/, "Intent"],
    [/^Note: (.+)$/, "Note"],
    [/^Classified in scope(.*)$/, "In scope"],
    [/^Classified out of scope(.*)$/, "Out of scope"],
    [/^Categories: (.+)$/, "Categories"],
    [/^Query: (.+)$/, "Planned query"],
    [/^No search required(.*)$/, "No search"],
    [/^No external retrieval(.*)$/, "Model knowledge"],
    [/^Ran (\d+ search.+)$/, "Searched"],
    [/^(\d+ unique results.+)$/, "Results"],
    [/^Assessed (.+)$/, "Assessed source"],
    [/^Evidence gap: (.+)$/, "Evidence gap"],
    [/^Conflicting claims(.*)$/, "Conflict"],
    [/^Perspective: (.+)$/, "Perspective"],
    [/^Consensus: (.+)$/, "Consensus"],
    [/^Claim checked: (.+)$/, "Checked claim"],
    [/^Flagged as uncertain: (.+)$/, "Flagged uncertain"],
    [/^Drafted response(.+)$/, "Drafted"],
    [/^Neutrality self-check: (.+)$/, "Neutrality check"],
    [/^Revised: (.+)$/, "Revised"],
    [/^Redirect to (.+)$/, "Redirect"],
  ];

  for (const [pattern, label] of patterns) {
    const match = text.match(pattern);
    if (match) {
      const content = match[1]?.trim();
      return { label, content: content || text };
    }
  }
  return { label: null, content: text };
}

interface Props {
  message: AssistantMessage;
  selectedStageId: string | undefined;
  onSelectStage: (stageId: string) => void;
}

export default function TraceCard({ message, selectedStageId, onSelectStage }: Props) {
  const { traceEvents, status } = message;
  const stages = dedupeByStage(traceEvents);
  const isRunning = status === "running";

  const completedIds = new Set(
    traceEvents.filter(e => e.status === "completed").map(e => e.stage_id)
  );
  const lastStarted = [...traceEvents].reverse().find(e => e.status === "started");
  const activeId =
    lastStarted && !completedIds.has(lastStarted.stage_id) ? lastStarted.stage_id : null;

  // Staggered micro-event reveal — only animates for active runs.
  // Historical messages show all events immediately.
  const [visibleCounts, setVisibleCounts] = useState<Record<string, number>>({});
  const scheduledRef = useRef<Record<string, number>>({});

  // Build a stable key that changes only when micro-event counts change.
  const stageKey = stages.map(s => `${s.stage_id}:${(s.micro_events ?? []).length}`).join("|");

  useEffect(() => {
    if (!isRunning) {
      scheduledRef.current = {};
      setVisibleCounts({});
      return;
    }

    const timers: ReturnType<typeof setTimeout>[] = [];

    stages.forEach(e => {
      const events = e.micro_events ?? [];
      const alreadyScheduled = scheduledRef.current[e.stage_id] ?? 0;
      for (let i = alreadyScheduled; i < events.length; i++) {
        const delay = (i - alreadyScheduled) * 160 + 80;
        const stageId = e.stage_id;
        const idx = i;
        const t = setTimeout(() => {
          setVisibleCounts(prev => ({
            ...prev,
            [stageId]: Math.max(prev[stageId] ?? 0, idx + 1),
          }));
        }, delay);
        timers.push(t);
      }
      scheduledRef.current[e.stage_id] = events.length;
    });

    return () => timers.forEach(clearTimeout);
  // stageKey captures all meaningful changes to stages; safe to omit `stages` itself
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isRunning, stageKey]);

  return (
    <div className="pl-3 border-l-2 border-border/40 space-y-3 py-1">
      {/* Loading state before first event */}
      {stages.length === 0 && isRunning && (
        <div className="flex items-center gap-2 text-xs text-muted/50">
          <span className="flex gap-0.5 items-center">
            {[0, 1, 2].map(i => (
              <span
                key={i}
                className="w-1 h-1 rounded-full bg-accent/50 animate-pulse"
                style={{ animationDelay: `${i * 150}ms` }}
              />
            ))}
          </span>
          <span>Working…</span>
        </div>
      )}

      {stages.map(e => {
        const isComplete = e.status === "completed";
        const isActive = e.stage_id === activeId;
        const isSelected = e.stage_id === selectedStageId;
        const microEvents = e.micro_events ?? [];

        // Historical messages show all events; running messages use staggered reveal.
        const visibleCount = isRunning ? (visibleCounts[e.stage_id] ?? 0) : microEvents.length;
        const visibleEvents = microEvents.slice(0, visibleCount);

        return (
          <div key={e.stage_id} className="space-y-1.5">
            {/* Stage row */}
            <button
              type="button"
              onClick={() => onSelectStage(e.stage_id)}
              className={[
                "w-full text-left flex items-center gap-2 group transition-colors py-0.5",
                isSelected ? "opacity-100" : "hover:opacity-80",
              ].join(" ")}
            >
              {/* Status indicator */}
              <span className="flex-shrink-0 w-3.5 flex items-center justify-center">
                {isComplete ? (
                  <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
                    <circle
                      cx="5" cy="5" r="4.5"
                      fill="rgb(22 101 52 / 0.4)"
                      stroke="rgb(74 222 128 / 0.4)"
                      strokeWidth="0.5"
                    />
                    <path
                      d="M2.5 5L4 6.5L7.5 3"
                      stroke="rgb(74 222 128 / 0.8)"
                      strokeWidth="1.2"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </svg>
                ) : isActive ? (
                  <span className="w-2 h-2 rounded-full bg-accent/70 active-stage-pulse" />
                ) : (
                  <span className="w-2 h-2 rounded-full border border-border/50" />
                )}
              </span>

              {/* Label */}
              <span
                className={[
                  "flex-1 text-xs leading-none",
                  isComplete
                    ? "text-text/45"
                    : isActive
                    ? "text-text/75 active-stage-breathe"
                    : "text-muted/35",
                ].join(" ")}
              >
                {e.label}
              </span>

              {/* Duration */}
              {isComplete && e.duration_ms != null && (
                <span className="text-[10px] text-muted/35 tabular-nums flex-shrink-0">
                  {formatDuration(e.duration_ms)}
                </span>
              )}

              {/* Selection indicator */}
              {isSelected && (
                <span className="w-0.5 h-3 rounded-full bg-accent/50 flex-shrink-0" />
              )}
            </button>

            {/* Micro-events */}
            {visibleEvents.length > 0 && (
              <div className="pl-5 space-y-1.5">
                {visibleEvents.map(me => {
                  const { label, content } = parseMicroEvent(me);
                  return (
                    <p
                      key={me.id}
                      className={`text-[11px] leading-relaxed micro-event-enter ${microEventColor(me.kind)}`}
                    >
                      {label && (
                        <span className="text-muted/35 mr-1.5 font-medium">{label}:</span>
                      )}
                      <span>{content}</span>
                    </p>
                  );
                })}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
