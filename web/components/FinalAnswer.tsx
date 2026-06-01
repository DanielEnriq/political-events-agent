"use client";

import { useState } from "react";
import type { CompletePayload, NeutralityCheck } from "@/lib/types";

function NeutralityBadge({ check }: { check: NeutralityCheck }) {
  const checks = [
    ["Avoided unsolicited opinion", check.avoided_unsolicited_opinion],
    ["Factually accurate", check.factually_accurate_and_comprehensive],
    ["Steelmanned perspectives", check.steelmanned_each_perspective],
    ["Neutral terminology", check.neutral_terminology_used],
    ["Equal depth", check.equal_depth_across_perspectives],
    ["Respectful tone", check.respectful_tone],
  ] as [string, boolean][];

  const passed = checks.filter(([, v]) => v).length;
  const total = checks.length;
  const allGood = passed === total;

  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-xs font-semibold uppercase tracking-widest text-muted">
          Neutrality Check
        </h3>
        <span
          className={`text-xs font-medium px-2 py-0.5 rounded-full ${
            allGood
              ? "bg-green-900/40 text-green-400"
              : "bg-yellow-900/40 text-yellow-400"
          }`}
        >
          {passed}/{total}
        </span>
      </div>
      <ul className="space-y-1">
        {checks.map(([label, ok]) => (
          <li key={label} className="flex items-center gap-2 text-xs">
            <span className={ok ? "text-green-400" : "text-red-400"}>
              {ok ? "✓" : "✗"}
            </span>
            <span className={ok ? "text-text/70" : "text-muted"}>{label}</span>
          </li>
        ))}
      </ul>
      {check.revisions_made.length > 0 && (
        <div className="mt-3 pt-3 border-t border-border">
          <p className="text-xs text-muted mb-1">Revisions made:</p>
          <ul className="space-y-1">
            {check.revisions_made.map((r, i) => (
              <li key={i} className="text-xs text-text/60">
                — {r}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

interface Props {
  result: CompletePayload;
  showRaw: boolean;
}

export default function FinalAnswer({ result, showRaw }: Props) {
  const [rawOpen, setRawOpen] = useState(false);

  return (
    <div className="space-y-3">
      {result.citations.length > 0 && (
        <div className="rounded-lg border border-border bg-surface p-4">
          <h3 className="text-xs font-semibold uppercase tracking-widest text-muted mb-3">
            Sources
          </h3>
          <ul className="space-y-2">
            {result.citations.map((c, i) => (
              <li key={i} className="text-sm">
                <a
                  href={c.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-accent hover:underline font-medium"
                >
                  {c.label}
                </a>
                {c.used_for_claim && (
                  <span className="text-muted ml-1.5 text-xs">
                    — {c.used_for_claim}
                  </span>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}

      {result.neutrality && <NeutralityBadge check={result.neutrality} />}

      {result.residual_uncertainty && (
        <div className="rounded-lg border border-border bg-surface p-4">
          <h3 className="text-xs font-semibold uppercase tracking-widest text-muted mb-2">
            Residual Uncertainty
          </h3>
          <p className="text-sm text-text/70">{result.residual_uncertainty}</p>
        </div>
      )}

      {result.suggested_followups.length > 0 && (
        <div className="rounded-lg border border-border bg-surface p-4">
          <h3 className="text-xs font-semibold uppercase tracking-widest text-muted mb-2">
            Follow-ups
          </h3>
          <ul className="space-y-1">
            {result.suggested_followups.map((f, i) => (
              <li key={i} className="text-sm text-text/70">
                → {f}
              </li>
            ))}
          </ul>
        </div>
      )}

      {showRaw && (
        <div className="rounded-lg border border-border bg-surface">
          <button
            onClick={() => setRawOpen((o) => !o)}
            className="w-full text-left px-4 py-2 text-xs text-muted hover:text-text transition-colors flex items-center justify-between"
          >
            <span className="font-semibold uppercase tracking-widest">
              Raw JSON
            </span>
            <span>{rawOpen ? "▲" : "▼"}</span>
          </button>
          {rawOpen && (
            <pre className="px-4 pb-4 text-xs text-text/60 overflow-auto max-h-80 whitespace-pre-wrap break-all">
              {JSON.stringify(result, null, 2)}
            </pre>
          )}
        </div>
      )}
    </div>
  );
}
