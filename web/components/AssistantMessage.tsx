"use client";

import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import type { AssistantMessage as AssistantMsg, CompletePayload } from "@/lib/types";
import TraceCard from "./TraceCard";

function hostname(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

// ── InlineAnswer ──────────────────────────────────────────────────────────────
// Full markdown rendered immediately; container fades/slides in via CSS animation.

function InlineAnswer({
  result,
  showRaw,
  onFollowUp,
}: {
  result: CompletePayload;
  showRaw: boolean;
  onFollowUp?: (text: string) => void;
}) {
  const [uncertaintyOpen, setUncertaintyOpen] = useState(false);

  const n = result.neutrality;
  const neutralityChecks = n
    ? [
        n.avoided_unsolicited_opinion,
        n.factually_accurate_and_comprehensive,
        n.steelmanned_each_perspective,
        n.neutral_terminology_used,
        n.equal_depth_across_perspectives,
        n.respectful_tone,
        ...(n.evidence_proportional_to_sources !== undefined
          ? [n.evidence_proportional_to_sources]
          : []),
      ]
    : null;
  const neutralityPassed = neutralityChecks ? neutralityChecks.filter(Boolean).length : null;
  const neutralityTotal = neutralityChecks ? neutralityChecks.length : 6;

  return (
    <div className="answer-enter space-y-4">
      {/* Answer body */}
      <div className="answer-prose text-sm">
        <ReactMarkdown>{result.answer}</ReactMarkdown>
      </div>

      {/* Neutrality badge */}
      {n && neutralityPassed !== null && (
        <div className="flex items-center gap-2.5 flex-wrap">
          <span
            className={`text-[11px] px-2 py-0.5 rounded font-medium ${
              neutralityPassed === neutralityTotal
                ? "bg-green-900/30 text-green-400/90"
                : "bg-yellow-900/30 text-yellow-400/90"
            }`}
          >
            Neutrality {neutralityPassed}/{neutralityTotal}
          </span>
          {n.revisions_made.length > 0 && (
            <span className="text-[11px] text-muted/55">
              {n.revisions_made.length} revision
              {n.revisions_made.length !== 1 ? "s" : ""} made
            </span>
          )}
        </div>
      )}

      {/* Citations — compact source rows */}
      {result.citations.length > 0 && (
        <div className="border-t border-border/30 pt-3 space-y-1.5">
          <p className="text-[11px] font-medium text-muted/55 uppercase tracking-wider mb-2">
            Sources
          </p>
          <ul className="space-y-1">
            {result.citations.map((c, i) => {
              const domain = hostname(c.url);
              return (
                <li
                  key={i}
                  className="group px-2.5 py-2 rounded border border-border/25 hover:border-accent/30 hover:bg-white/[0.03] transition-all space-y-0.5"
                >
                  <div className="flex items-start gap-1.5 min-w-0">
                    <a
                      href={c.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-[12px] text-accent/90 hover:text-accent font-medium leading-snug flex-1 min-w-0 transition-colors"
                    >
                      {c.label}
                    </a>
                    <span className="text-[10px] text-muted/50 group-hover:text-muted/70 flex-shrink-0 mt-px transition-colors">
                      {domain}
                    </span>
                  </div>
                  {c.used_for_claim && (
                    <p className="text-[11px] text-muted/55 leading-snug">
                      Used for: {c.used_for_claim}
                    </p>
                  )}
                </li>
              );
            })}
          </ul>
        </div>
      )}

      {/* Residual uncertainty — collapsed by default */}
      {result.residual_uncertainty && (
        <div className="border-t border-border/20 pt-2">
          <div className="flex items-center justify-between gap-3">
            <span className="text-[11px] text-muted/45 leading-none">
              Evidence limitations noted
            </span>
            <button
              type="button"
              onClick={() => setUncertaintyOpen((o) => !o)}
              aria-expanded={uncertaintyOpen}
              aria-label={uncertaintyOpen ? "Hide uncertainty details" : "Show uncertainty details"}
              className="text-[11px] text-muted/40 hover:text-muted/70 transition-colors flex-shrink-0"
            >
              {uncertaintyOpen ? "Hide" : "Show"}
            </button>
          </div>
          {uncertaintyOpen && (
            <p className="mt-2 text-[12px] text-muted/75 leading-relaxed pl-3 border-l-2 border-border/40">
              {result.residual_uncertainty}
            </p>
          )}
        </div>
      )}

      {/* Follow-ups */}
      {result.suggested_followups.length > 0 && (
        <div className="border-t border-border/30 pt-3 space-y-1.5">
          <p className="text-[11px] text-muted/50 uppercase tracking-wider mb-2">
            Follow-ups
          </p>
          {result.suggested_followups.slice(0, 3).map((f, i) => (
            <button
              key={i}
              type="button"
              onClick={() => onFollowUp?.(f)}
              className="group block w-full text-left text-[12px] text-muted/75 hover:text-text/85 hover:bg-white/[0.03] px-3 py-2 rounded-md transition-colors cursor-pointer border border-border/20 hover:border-accent/30"
            >
              <span className="text-accent/50 group-hover:text-accent/80 mr-1.5 transition-colors">→</span>
              {f}
            </button>
          ))}
        </div>
      )}

      {/* Raw JSON */}
      {showRaw && (
        <details className="border-t border-border/30 pt-3">
          <summary className="text-[11px] text-muted/50 cursor-pointer hover:text-muted select-none">
            Raw payload
          </summary>
          <pre className="mt-2 text-[11px] text-text/35 overflow-auto max-h-48 whitespace-pre-wrap break-all leading-relaxed">
            {JSON.stringify(result, null, 2)}
          </pre>
        </details>
      )}
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

interface Props {
  message: AssistantMsg;
  selectedStageId: string | undefined;
  onSelectStage: (stageId: string) => void;
  onFollowUp: (text: string) => void;
  showRaw: boolean;
}

export default function AssistantMessageView({
  message,
  selectedStageId,
  onSelectStage,
  onFollowUp,
  showRaw,
}: Props) {
  // Trace: expanded while running, collapsed to compact summary row after done.
  // Historical messages (status === "done" on mount) start collapsed.
  const [traceOpen, setTraceOpen] = useState(message.status === "running");

  // Track whether this message was ever live to avoid auto-scrolling historical loads.
  const wasRunningRef = useRef(message.status === "running");
  const scrolledRef = useRef(false);
  const answerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (message.status === "running") wasRunningRef.current = true;
  }, [message.status]);

  // Collapse trace once the run completes.
  useEffect(() => {
    if (message.status === "done") setTraceOpen(false);
  }, [message.status]);

  // One-time scroll to answer start. Delayed 320ms to let the trace collapse
  // animation (280ms) settle before the viewport shifts.
  useEffect(() => {
    if (
      message.status === "done" &&
      message.result &&
      wasRunningRef.current &&
      !scrolledRef.current
    ) {
      scrolledRef.current = true;
      const t = setTimeout(() => {
        answerRef.current?.scrollIntoView({ block: "start", behavior: "smooth" });
      }, 320);
      return () => clearTimeout(t);
    }
  }, [message.status, message.result]);

  if (message.status === "error") {
    if (message.errorKind === "interrupted") {
      return (
        <div className="w-full rounded-xl px-4 py-3 bg-surface border border-border/50 space-y-0.5">
          <p className="text-xs font-medium text-muted/60">Run interrupted</p>
          <p className="text-xs text-muted/40 leading-relaxed">
            This run didn&apos;t complete. Start a new message to continue.
          </p>
        </div>
      );
    }
    return (
      <div className="w-full rounded-2xl rounded-bl-sm px-4 py-3 bg-red-900/20 border border-red-800/30 text-sm text-red-300/90 leading-relaxed">
        {message.error ?? "An error occurred."}
      </div>
    );
  }

  const hasTrace = message.traceEvents.length > 0 || message.status === "running";
  const isDone = message.status === "done";

  // Compact summary data
  const stageCount = new Set(message.traceEvents.map(e => e.stage_id)).size;
  const citationCount = message.result?.citations.length ?? 0;
  const sn = message.result?.neutrality;
  const snChecks = sn
    ? [
        sn.avoided_unsolicited_opinion,
        sn.factually_accurate_and_comprehensive,
        sn.steelmanned_each_perspective,
        sn.neutral_terminology_used,
        sn.equal_depth_across_perspectives,
        sn.respectful_tone,
        ...(sn.evidence_proportional_to_sources !== undefined
          ? [sn.evidence_proportional_to_sources]
          : []),
      ]
    : null;
  const snPassed = snChecks?.filter(Boolean).length ?? null;
  const snTotal = snChecks?.length ?? null;

  return (
    <div className="w-full space-y-2">
      {/* Agent activity trace */}
      {hasTrace && (
        <div>
          {isDone ? (
            // Compact summary toggle + animated full trace below
            <div>
              <button
                type="button"
                onClick={() => setTraceOpen(o => !o)}
                className="flex items-center gap-2 w-full text-left text-[11px] text-muted/60 hover:text-muted/85 transition-all pl-3 border-l-2 border-border/30 hover:border-accent/35 hover:bg-white/[0.025] py-1.5 rounded-r group"
              >
                <span className="font-medium">Audit trace</span>
                {stageCount > 0 && (
                  <>
                    <span className="text-muted/35">·</span>
                    <span>{stageCount} stages</span>
                  </>
                )}
                {snPassed !== null && snTotal !== null && (
                  <>
                    <span className="text-muted/35">·</span>
                    <span>Neutrality {snPassed}/{snTotal}</span>
                  </>
                )}
                {citationCount > 0 && (
                  <>
                    <span className="text-muted/35">·</span>
                    <span>{citationCount} source{citationCount !== 1 ? "s" : ""}</span>
                  </>
                )}
                {/* Rotating chevron */}
                <svg
                  className="ml-auto opacity-50 group-hover:opacity-80 flex-shrink-0"
                  style={{
                    transform: traceOpen ? "rotate(180deg)" : "rotate(0deg)",
                    transition: "transform 220ms ease, opacity 120ms ease",
                  }}
                  width="12"
                  height="12"
                  viewBox="0 0 12 12"
                  fill="none"
                >
                  <path
                    d="M3 4.5L6 7.5L9 4.5"
                    stroke="currentColor"
                    strokeWidth="1.4"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
              </button>

              {/* Animated collapse panel — always mounted so inspector interactions survive */}
              <div
                className="trace-collapse-panel"
                data-open={traceOpen ? "true" : "false"}
              >
                <div className="trace-collapse-inner">
                  <div className="pt-2">
                    <TraceCard
                      message={message}
                      selectedStageId={selectedStageId}
                      onSelectStage={onSelectStage}
                    />
                  </div>
                </div>
              </div>
            </div>
          ) : (
            // Running — always show full live trace
            <TraceCard
              message={message}
              selectedStageId={selectedStageId}
              onSelectStage={onSelectStage}
            />
          )}
        </div>
      )}

      {/* Final answer — centered readable column */}
      {isDone && message.result && (
        <div ref={answerRef} className="answer-column pt-1">
          <InlineAnswer
            result={message.result}
            showRaw={showRaw}
            onFollowUp={onFollowUp}
          />
        </div>
      )}
    </div>
  );
}
