"use client";

import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import type { AssistantMessage as AssistantMsg, CompletePayload } from "@/lib/types";
import TraceCard from "./TraceCard";

// ── Answer fade-in — renders full Markdown immediately, fades in smoothly ─────

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

  useEffect(() => {
    const id = requestAnimationFrame(() => setVisible(true));
    return () => cancelAnimationFrame(id);
  }, []);

  const n = result.neutrality;
  const neutralityPassed = n
    ? [
        n.avoided_unsolicited_opinion,
        n.factually_accurate_and_comprehensive,
        n.steelmanned_each_perspective,
        n.neutral_terminology_used,
        n.equal_depth_across_perspectives,
        n.respectful_tone,
      ].filter(Boolean).length
    : null;
  const neutralityTotal = 6;

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
        <div className="border-t border-border/30 pt-3 space-y-2">
          <p className="text-[11px] font-medium text-muted/60 uppercase tracking-wider">
            Sources
          </p>
          <ul className="space-y-2">
            {result.citations.map((c, i) => (
              <li key={i} className="flex gap-2 text-[12px]">
                <span className="text-muted/35 flex-shrink-0 mt-0.5">↗</span>
                <span className="min-w-0">
                  <a
                    href={c.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-accent hover:underline"
                  >
                    {c.label}
                  </a>
                  {c.used_for_claim && (
                    <span className="text-muted/55 ml-1.5 leading-relaxed">
                      — {c.used_for_claim}
                    </span>
                  )}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Residual uncertainty */}
      {result.residual_uncertainty && (
        <div className="border-l-2 border-border/50 pl-3 py-0.5">
          <p className="text-[12px] text-muted/65 italic leading-relaxed">
            {result.residual_uncertainty}
          </p>
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
              className="block w-full text-left text-[12px] text-muted/65 hover:text-accent hover:bg-accent/5 px-2.5 py-1.5 rounded-md transition-colors cursor-pointer border border-transparent hover:border-accent/20"
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
