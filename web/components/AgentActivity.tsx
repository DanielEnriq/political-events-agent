"use client";

import type { ProgressEvent } from "@/lib/types";

const TOTAL_STAGES = 7;

function statusIcon(status: ProgressEvent["status"], isActive: boolean) {
  if (status === "completed") {
    return (
      <span className="flex-shrink-0 w-5 h-5 rounded-full bg-green-800/60 flex items-center justify-center text-green-400 text-[10px] font-bold">
        ✓
      </span>
    );
  }
  if (isActive) {
    return (
      <span className="flex-shrink-0 w-5 h-5 rounded-full border border-accent/60 flex items-center justify-center">
        <span className="w-2 h-2 rounded-full bg-accent animate-pulse" />
      </span>
    );
  }
  return (
    <span className="flex-shrink-0 w-5 h-5 rounded-full border border-border flex items-center justify-center">
      <span className="w-1.5 h-1.5 rounded-full bg-muted/40" />
    </span>
  );
}

interface Props {
  events: ProgressEvent[];
  running: boolean;
}

export default function AgentActivity({ events, running }: Props) {
  // Deduplicate: keep latest status per stage_id
  const stageMap = new Map<string, ProgressEvent>();
  for (const e of events) {
    const existing = stageMap.get(e.stage_id);
    if (!existing || e.status === "completed") {
      stageMap.set(e.stage_id, e);
    }
  }
  const stages = Array.from(stageMap.values());

  const lastEvent = events[events.length - 1];
  const activeId = lastEvent?.status === "started" ? lastEvent.stage_id : null;

  if (stages.length === 0 && !running) return null;

  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <h3 className="text-xs font-semibold uppercase tracking-widest text-muted mb-3">
        Pipeline
      </h3>
      <div className="space-y-2">
        {stages.map((e) => {
          const isActive = e.stage_id === activeId;
          const isComplete = e.status === "completed";
          return (
            <div key={e.stage_id} className="flex items-center gap-3">
              {statusIcon(e.status, isActive)}
              <span
                className={`text-sm flex-1 ${
                  isComplete
                    ? "text-text/70"
                    : isActive
                    ? "text-text"
                    : "text-muted"
                }`}
              >
                {e.label}
              </span>
              {isComplete && e.duration_ms != null && (
                <span className="text-xs text-muted tabular-nums">
                  {(e.duration_ms / 1000).toFixed(1)}s
                </span>
              )}
            </div>
          );
        })}
        {running && stages.length === 0 && (
          <div className="flex items-center gap-3">
            <span className="flex-shrink-0 w-5 h-5 rounded-full border border-accent/60 flex items-center justify-center">
              <span className="w-2 h-2 rounded-full bg-accent animate-pulse" />
            </span>
            <span className="text-sm text-text">Starting…</span>
          </div>
        )}
      </div>
      {running && (
        <div className="mt-3 pt-3 border-t border-border">
          <div className="h-1 bg-border rounded-full overflow-hidden">
            <div
              className="h-full bg-accent/60 rounded-full transition-all duration-500"
              style={{
                width: `${Math.round(
                  (stages.filter((e) => e.status === "completed").length /
                    TOTAL_STAGES) *
                    100
                )}%`,
              }}
            />
          </div>
        </div>
      )}
    </div>
  );
}
