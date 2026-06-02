"use client";

import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import type { AssistantMessage as AssistantMsg, CompletePayload } from "@/lib/types";
import TraceCard from "./TraceCard";

// ── Answer fade-in — renders full Markdown immediately, fades in smoothly ─────

function hostname(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

function InlineAnswer({
  result,
  showRaw,
  onFollowUp,
}: {
  result: CompletePayload;
  showRaw: boolean;
  onFollowUp?: (text: string) => void;
}) {
  const [visible, setVisible] = useState(false);
  const [uncertaintyOpen, setUncertaintyOpen] = useState(false);

  useEffect(() => {
    const id = requestAnimationFrame(() => setVisible(true));
    return () => cancelAnimationFrame(id);
  }, []);

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
    <div
      className={`space-y-4 transition-opacity duration-400 ease-out ${
        visible ? "opacity-100" : "opacity-0"
      }`}
    >
      {/* Answer body — full Markdown rendered immediately */}
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

      {/* Citations */}
      {result.citations.length > 0 && (
        <div className="border-t border-border/30 pt-3 space-y-1.5">
          <p className="text-[11px] font-medium text-muted/60 uppercase tracking-wider mb-2">
            Sources
          </p>
          <ul className="space-y-2">
            {result.citations.map((c, i) => {
              const domain = hostname(c.url);
              return (
                <li key={i} className="rounded border border-border/30 bg-surface/20 px-2.5 py-2 space-y-0.5">
                  <div className="flex items-start gap-1.5 min-w-0">
                    <a
                      href={c.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-[12px] text-accent hover:underline font-medium leading-snug flex-1 min-w-0"
                    >
                      {c.label}
                    </a>
                    <span className="text-[10px] text-muted/40 flex-shrink-0 mt-px">{domain}</span>
                  </div>
                  {c.used_for_claim && (
                    <p className="text-[11px] text-muted/50 leading-snug">
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
              aria-label={
                uncertaintyOpen ? "Hide uncertainty details" : "Show uncertainty details"
              }
              className="text-[11px] text-muted/40 hover:text-muted/70 transition-colors flex-shrink-0"
            >
              {uncertaintyOpen ? "Hide" : "Show"}
            </button>
          </div>
          {uncertaintyOpen && (
            <p className="mt-2 text-[12px] text-muted/55 italic leading-relaxed pl-2 border-l border-border/30">
              {result.residual_uncertainty}
            </p>
          )}
        </div>
      )}

      {/* Follow-ups — clickable */}
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
              className="block w-full text-left text-[12px] text-muted/65 hover:text-accent hover:bg-accent/8 px-3 py-2 rounded-md transition-colors cursor-pointer border border-transparent hover:border-accent/25"
            >
              <span className="text-muted/40 mr-1.5">→</span>
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
  if (message.status === "error") {
    if (message.errorKind === "interrupted") {
      return (
        <div className="w-full rounded-xl px-4 py-3 bg-surface border border-border/50 space-y-0.5">
          <p className="text-xs font-medium text-muted/60">Run interrupted</p>
          <p className="text-xs text-muted/40 leading-relaxed">
            This run didn't complete. Start a new message to continue.
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

  return (
    <div className="w-full space-y-3">
      {/* Agent activity — left-rail integrated trace */}
      {hasTrace && (
        <TraceCard
          message={message}
          selectedStageId={selectedStageId}
          onSelectStage={onSelectStage}
        />
      )}

      {/* Final answer — full-width, integrated */}
      {isDone && message.result && (
        <div className="pt-1">
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
