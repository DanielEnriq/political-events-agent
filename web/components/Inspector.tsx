"use client";

import type { ChatMessage, ProgressEvent, SelectedStage, StageDetails } from "@/lib/types";
import { isAssistant } from "@/lib/types";

// ── Stage metadata ────────────────────────────────────────────────────────────

const STAGE_META: Record<string, { title: string; description: string }> = {
  s1_intake: {
    title: "S1 — Intake",
    description:
      "Normalises the query, identifies modality (factual, opinion, boundary, multi-turn), and extracts stated stances.",
  },
  s2_scope: {
    title: "S2 — Scope",
    description:
      "Reasons whether the query falls within the political-events domain. If out of scope, the pipeline short-circuits here.",
  },
  s3_plan_search: {
    title: "S3 — Search Plan",
    description:
      "Decides whether live web search is needed. If yes, generates targeted queries and specifies source types.",
  },
  search_execution: {
    title: "Search Execution",
    description:
      "Runs the planned queries against the search provider and collects raw results.",
  },
  s4_source_quality: {
    title: "S4 — Evidence",
    description:
      "Assesses authority, recency, editorial slant, and relevance for each retrieved source. When no search was performed, calibrates model-knowledge limitations instead.",
  },
  s5_perspectives: {
    title: "S5 — Perspectives",
    description:
      "Maps distinct political viewpoints, steelmans each perspective, and identifies areas of consensus and disagreement.",
  },
  s6_verification: {
    title: "S6 — Verification",
    description:
      "Calibrates confidence in factual claims, flags unsupported assertions, and attaches appropriate hedging.",
  },
  s7_compose_check: {
    title: "S7 — Compose & Self-check",
    description:
      "Drafts the final response and runs a 6-point neutrality self-check. Revisions are recorded if the draft fails any criterion.",
  },
};

function formatMs(ms: number | null): string | null {
  if (ms == null) return null;
  return ms >= 1000 ? `${(ms / 1000).toFixed(2)}s` : `${ms}ms`;
}

// ── Shared sub-components ─────────────────────────────────────────────────────

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <p className="text-[10px] font-semibold text-muted/60 uppercase tracking-widest mb-1.5">
      {children}
    </p>
  );
}

function InfoRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-2 text-xs py-1.5 border-b border-border/20 last:border-0">
      <span className="text-muted flex-shrink-0">{label}</span>
      <span className="text-text/70 text-right min-w-0 break-words">{value}</span>
    </div>
  );
}

function Pill({ children, color = "default" }: { children: React.ReactNode; color?: "default" | "green" | "yellow" | "red" }) {
  const cls = {
    default: "bg-surface/60 text-muted/80",
    green: "bg-green-900/30 text-green-400/90",
    yellow: "bg-yellow-900/30 text-yellow-400/90",
    red: "bg-red-900/30 text-red-400/90",
  }[color];
  return (
    <span className={`inline-block px-1.5 py-0.5 rounded text-[10px] font-medium ${cls}`}>
      {children}
    </span>
  );
}

function StringList({ items }: { items: string[] }) {
  if (!items.length) return <span className="text-muted/40 text-xs italic">—</span>;
  return (
    <ul className="space-y-1">
      {items.map((s, i) => (
        <li key={i} className="text-xs text-text/60 leading-relaxed pl-1 border-l border-border/30">
          {s}
        </li>
      ))}
    </ul>
  );
}

// ── Per-stage detail panels ───────────────────────────────────────────────────

function S1Detail({ d }: { d: NonNullable<StageDetails["s1_intake"]> }) {
  return (
    <div className="space-y-3">
      <div>
        <SectionLabel>Canonical query</SectionLabel>
        <p className="text-xs text-text/70 leading-relaxed">
          {d.canonical_query ?? <span className="text-muted/40 italic">—</span>}
        </p>
      </div>
      {d.modality && (
        <div>
          <SectionLabel>Modality</SectionLabel>
          <Pill>{d.modality}</Pill>
        </div>
      )}
      {d.notes && (
        <div>
          <SectionLabel>Notes</SectionLabel>
          <p className="text-xs text-text/50 leading-relaxed italic">{d.notes}</p>
        </div>
      )}
    </div>
  );
}

function S2Detail({ d }: { d: NonNullable<StageDetails["s2_scope"]> }) {
  return (
    <div className="space-y-3">
      <div className="rounded border border-border/50 divide-y divide-border/20">
        <InfoRow
          label="Decision"
          value={
            d.in_scope != null ? (
              <Pill color={d.in_scope ? "green" : "yellow"}>
                {d.in_scope ? "In scope" : "Out of scope"}
              </Pill>
            ) : "—"
          }
        />
        {d.confidence != null && (
          <InfoRow label="Confidence" value={`${d.confidence} / 5`} />
        )}
      </div>
      {d.matched_charter_categories.length > 0 && (
        <div>
          <SectionLabel>Charter categories</SectionLabel>
          <div className="flex flex-wrap gap-1">
            {d.matched_charter_categories.map((c, i) => (
              <Pill key={i}>{c}</Pill>
            ))}
          </div>
        </div>
      )}
      {d.reasoning && (
        <div>
          <SectionLabel>Reasoning</SectionLabel>
          <p className="text-xs text-text/60 leading-relaxed">{d.reasoning}</p>
        </div>
      )}
      {d.suggested_redirect && (
        <div>
          <SectionLabel>Redirect</SectionLabel>
          <p className="text-xs text-text/60 leading-relaxed italic">{d.suggested_redirect}</p>
        </div>
      )}
    </div>
  );
}

function S3Detail({ d }: { d: NonNullable<StageDetails["s3_plan_search"]> }) {
  return (
    <div className="space-y-3">
      {/* Decision — shown first */}
      <div className="flex items-center gap-2">
        <Pill color={d.needs_search ? "yellow" : "green"}>
          {d.needs_search ? "Search required" : "Model knowledge sufficient"}
        </Pill>
      </div>
      {/* Rationale next */}
      {d.rationale && (
        <div>
          <SectionLabel>Rationale</SectionLabel>
          <p className="text-xs text-text/60 leading-relaxed">{d.rationale}</p>
        </div>
      )}
      {/* Queries */}
      {d.queries.length > 0 && (
        <div>
          <SectionLabel>Search queries ({d.queries.length})</SectionLabel>
          <StringList items={d.queries} />
        </div>
      )}
      {/* Target source types */}
      {d.target_source_types.length > 0 && (
        <div>
          <SectionLabel>Target source types</SectionLabel>
          <div className="flex flex-wrap gap-1">
            {d.target_source_types.map((t, i) => (
              <Pill key={i}>{t}</Pill>
            ))}
          </div>
        </div>
      )}
      {d.why_model_knowledge_insufficient && (
        <div>
          <SectionLabel>Why live search</SectionLabel>
          <p className="text-xs text-text/50 leading-relaxed italic">{d.why_model_knowledge_insufficient}</p>
        </div>
      )}
    </div>
  );
}

function SearchDetail({ d }: { d: NonNullable<StageDetails["search_execution"]> }) {
  return (
    <div className="space-y-3">
      <div className="rounded border border-border/50 divide-y divide-border/20">
        {d.queries_run != null && <InfoRow label="Queries run" value={d.queries_run} />}
        {d.raw_hits != null && <InfoRow label="Raw hits" value={d.raw_hits} />}
        {d.unique_hits != null && <InfoRow label="After dedup" value={d.unique_hits} />}
        {d.hits_passed != null && <InfoRow label="Passed to S4" value={d.hits_passed} />}
        {d.results_capped != null && (
          <InfoRow
            label="Capped"
            value={<Pill color={d.results_capped ? "yellow" : "green"}>{d.results_capped ? "Yes" : "No"}</Pill>}
          />
        )}
      </div>
      {d.domains.length > 0 && (
        <div>
          <SectionLabel>Sources fetched</SectionLabel>
          <StringList items={d.domains} />
        </div>
      )}
    </div>
  );
}

function S4Detail({ d }: { d: NonNullable<StageDetails["s4_source_quality"]> }) {
  const noSources = d.sources.length === 0;
  return (
    <div className="space-y-3">
      {/* Evidence confidence — shown first */}
      {d.confidence_in_evidence != null && (
        <div className="flex items-center gap-2">
          <span className="text-xs text-muted/70">Evidence confidence</span>
          <Pill
            color={
              d.confidence_in_evidence >= 4 ? "green" :
              d.confidence_in_evidence >= 2 ? "yellow" : "red"
            }
          >
            {d.confidence_in_evidence} / 5
          </Pill>
        </div>
      )}
      {/* Sources or model-knowledge note */}
      {noSources ? (
        <div className="rounded border border-border/40 px-3 py-2.5 bg-surface/30">
          <p className="text-xs text-muted/70 leading-relaxed">
            Evidence calibration (model knowledge) — no external sources were retrieved for this query.
          </p>
        </div>
      ) : (
        <div>
          <SectionLabel>Source assessments ({d.sources.length})</SectionLabel>
          <div className="space-y-2">
            {d.sources.map((s, i) => (
              <div key={i} className="rounded border border-border/30 px-2.5 py-2 space-y-1">
                <p className="text-xs font-medium text-text/70 truncate">{s.domain}</p>
                <div className="flex flex-wrap gap-1">
                  {s.source_type && <Pill>{s.source_type}</Pill>}
                  {s.slant && <Pill color="yellow">{s.slant}</Pill>}
                  {s.confidence != null && (
                    <Pill color={s.confidence >= 4 ? "green" : s.confidence >= 2 ? "yellow" : "red"}>
                      conf {s.confidence}/5
                    </Pill>
                  )}
                </div>
                {s.relevance && (
                  <p className="text-[11px] text-muted/60 leading-relaxed">{s.relevance}</p>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
      {d.gaps.length > 0 && (
        <div>
          <SectionLabel>Evidence gaps</SectionLabel>
          <StringList items={d.gaps} />
        </div>
      )}
      {d.conflicting_claims.length > 0 && (
        <div>
          <SectionLabel>Conflicting claims</SectionLabel>
          <StringList items={d.conflicting_claims} />
        </div>
      )}
    </div>
  );
}

function S5Detail({ d }: { d: NonNullable<StageDetails["s5_perspectives"]> }) {
  return (
    <div className="space-y-3">
      {/* Summary header — count of perspectives and consensus */}
      <div className="flex items-center gap-2 flex-wrap">
        <Pill>{d.perspectives.length} perspective{d.perspectives.length !== 1 ? "s" : ""} mapped</Pill>
        {d.areas_of_consensus.length > 0 && (
          <Pill color="green">{d.areas_of_consensus.length} consensus area{d.areas_of_consensus.length !== 1 ? "s" : ""}</Pill>
        )}
        {d.areas_of_disagreement.length > 0 && (
          <Pill color="yellow">{d.areas_of_disagreement.length} disagreement{d.areas_of_disagreement.length !== 1 ? "s" : ""}</Pill>
        )}
      </div>
      {/* Perspective cards */}
      {d.perspectives.map((p, i) => (
        <div key={i} className="rounded border border-border/30 px-2.5 py-2.5 space-y-2">
          <p className="text-xs font-semibold text-text/80">{p.label ?? `Perspective ${i + 1}`}</p>
          {p.core_claims.length > 0 && (
            <div>
              <SectionLabel>Core claims</SectionLabel>
              <StringList items={p.core_claims} />
            </div>
          )}
          {p.strongest_evidence.length > 0 && (
            <div>
              <SectionLabel>Strongest evidence</SectionLabel>
              <StringList items={p.strongest_evidence} />
            </div>
          )}
          {p.concerns.length > 0 && (
            <div>
              <SectionLabel>Concerns about others</SectionLabel>
              <StringList items={p.concerns} />
            </div>
          )}
        </div>
      ))}
      {/* Consensus */}
      {d.areas_of_consensus.length > 0 && (
        <div>
          <SectionLabel>Consensus</SectionLabel>
          <StringList items={d.areas_of_consensus} />
        </div>
      )}
      {/* Disagreement */}
      {d.areas_of_disagreement.length > 0 && (
        <div>
          <SectionLabel>Disagreement</SectionLabel>
          <StringList items={d.areas_of_disagreement} />
        </div>
      )}
      {d.empirical_vs_normative.length > 0 && (
        <div>
          <SectionLabel>Dispute types</SectionLabel>
          <div className="space-y-1">
            {d.empirical_vs_normative.map((e, i) => (
              <div key={i} className="flex items-start gap-2 text-xs">
                <Pill>{e.kind}</Pill>
                <span className="text-text/50 leading-relaxed">{e.claim}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function S6Detail({ d }: { d: NonNullable<StageDetails["s6_verification"]> }) {
  return (
    <div className="space-y-3">
      {/* Calibration note as a prominent callout — shown first */}
      {d.overall_calibration_note && (
        <div className="rounded border border-border/50 bg-surface/30 px-3 py-2.5">
          <p className="text-[10px] font-semibold text-muted/60 uppercase tracking-widest mb-1.5">
            Calibration note
          </p>
          <p className="text-xs text-text/65 leading-relaxed">{d.overall_calibration_note}</p>
        </div>
      )}
      {/* Factual claims */}
      {d.factual_claims.length > 0 && (
        <div>
          <SectionLabel>Factual claims ({d.factual_claims.length})</SectionLabel>
          <div className="space-y-2">
            {d.factual_claims.map((c, i) => (
              <div key={i} className="rounded border border-border/30 px-2.5 py-2 space-y-1">
                <p className="text-xs text-text/70 leading-relaxed">{c.claim}</p>
                <div className="flex flex-wrap gap-1">
                  {c.confidence != null && (
                    <Pill color={c.confidence >= 4 ? "green" : c.confidence >= 2 ? "yellow" : "red"}>
                      conf {c.confidence}/5
                    </Pill>
                  )}
                  {c.drop_if_uncorroborated && <Pill color="red">drop if uncorroborated</Pill>}
                </div>
                {c.suggested_hedging && (
                  <p className="text-[11px] text-muted/60 italic">{c.suggested_hedging}</p>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
      {/* Do not assert */}
      {d.things_i_should_not_assert.length > 0 && (
        <div>
          <SectionLabel>Do not assert</SectionLabel>
          <StringList items={d.things_i_should_not_assert} />
        </div>
      )}
    </div>
  );
}

function S7Detail({
  d,
  neutrality,
}: {
  d: NonNullable<StageDetails["s7_compose_check"]>;
  neutrality: {
    avoided_unsolicited_opinion: boolean;
    factually_accurate_and_comprehensive: boolean;
    steelmanned_each_perspective: boolean;
    neutral_terminology_used: boolean;
    equal_depth_across_perspectives: boolean;
    respectful_tone: boolean;
    revisions_made: string[];
  } | null;
}) {
  const neutralityRows: [string, boolean][] = neutrality
    ? [
        ["Avoided unsolicited opinion", neutrality.avoided_unsolicited_opinion],
        ["Factually accurate & comprehensive", neutrality.factually_accurate_and_comprehensive],
        ["Steelmanned each perspective", neutrality.steelmanned_each_perspective],
        ["Neutral terminology", neutrality.neutral_terminology_used],
        ["Equal depth across perspectives", neutrality.equal_depth_across_perspectives],
        ["Respectful tone", neutrality.respectful_tone],
      ]
    : [];

  return (
    <div className="space-y-3">
      {neutrality && (
        <div>
          <SectionLabel>Neutrality self-check</SectionLabel>
          <div className="space-y-1">
            {neutralityRows.map(([label, ok]) => (
              <div key={label} className="flex items-center gap-2 text-xs">
                <span className={ok ? "text-green-400 flex-shrink-0" : "text-red-400 flex-shrink-0"}>
                  {ok ? "✓" : "✗"}
                </span>
                <span className={ok ? "text-text/70" : "text-muted/60"}>{label}</span>
              </div>
            ))}
          </div>
        </div>
      )}
      {d.revisions_made.length > 0 && (
        <div>
          <SectionLabel>Revisions made</SectionLabel>
          <StringList items={d.revisions_made} />
        </div>
      )}
      {d.residual_uncertainty && (
        <div>
          <SectionLabel>Residual uncertainty</SectionLabel>
          <p className="text-xs text-text/60 leading-relaxed italic">{d.residual_uncertainty}</p>
        </div>
      )}
      {d.suggested_followups.length > 0 && (
        <div>
          <SectionLabel>Suggested follow-ups</SectionLabel>
          <StringList items={d.suggested_followups} />
        </div>
      )}
    </div>
  );
}

// ── Main Inspector ────────────────────────────────────────────────────────────

interface Props {
  selected: SelectedStage | null;
  messages: ChatMessage[];
}

export default function Inspector({ selected, messages }: Props) {
  if (!selected) {
    return (
      <div className="flex-1 flex items-center justify-center px-6 text-center">
        <p className="text-xs text-muted/50 leading-relaxed max-w-[160px]">
          Click a trace step to inspect its details.
        </p>
      </div>
    );
  }

  const msg = messages.find(m => m.id === selected.messageId);
  if (!msg || !isAssistant(msg)) {
    return (
      <div className="flex-1 flex items-center justify-center px-6">
        <p className="text-xs text-muted/50">Message not found.</p>
      </div>
    );
  }

  const stageEvents = msg.traceEvents.filter(e => e.stage_id === selected.stageId);
  const completedEvent = stageEvents.findLast(e => e.status === "completed");
  const startedEvent = stageEvents.findLast(e => e.status === "started");
  const latestEvent = completedEvent ?? startedEvent;

  const isComplete = !!completedEvent;
  const isActive = !completedEvent && !!startedEvent;
  const hasStarted = !!latestEvent;

  const meta = STAGE_META[selected.stageId];
  const duration = formatMs(completedEvent?.duration_ms ?? null);

  // Prefer final stage_details (available after complete event), fall back to
  // per-event detail emitted during streaming (available as each stage finishes).
  const finalStageDetails = msg.result?.stage_details;
  const eventDetail = completedEvent?.detail as Record<string, unknown> | undefined;

  function resolveDetail<T>(finalVal: T | undefined): T | Record<string, unknown> | null {
    return finalVal ?? (eventDetail as T | undefined) ?? null;
  }

  // For the active stage, look for any micro-events to show context.
  const activeSummary = isActive ? (startedEvent as ProgressEvent | undefined)?.summary : undefined;

  return (
    <div className="flex-1 overflow-y-auto p-4 space-y-4">
      {/* Stage title + description */}
      <div className="space-y-1.5">
        <div className="flex items-center gap-2">
          <span
            className={`w-2 h-2 rounded-full flex-shrink-0 ${
              isComplete
                ? "bg-green-500/80"
                : isActive
                ? "bg-accent animate-pulse"
                : "bg-muted/30"
            }`}
          />
          <h3 className="text-sm font-semibold text-text">
            {meta?.title ?? latestEvent?.label ?? selected.stageId}
          </h3>
        </div>
        {meta?.description && (
          <p className="text-xs text-muted/70 leading-relaxed pl-4">
            {meta.description}
          </p>
        )}
      </div>

      {/* Status + duration row */}
      {hasStarted && (
        <div className="rounded border border-border/50 divide-y divide-border/30 text-xs">
          <div className="flex items-center justify-between px-3 py-2">
            <span className="text-muted">Status</span>
            <span
              className={
                isComplete
                  ? "text-green-400"
                  : isActive
                  ? "text-accent"
                  : "text-muted/50"
              }
            >
              {isComplete ? "Completed" : isActive ? "In progress…" : "Pending"}
            </span>
          </div>
          {duration && (
            <div className="flex items-center justify-between px-3 py-2">
              <span className="text-muted">Duration</span>
              <span className="text-text/70 tabular-nums">{duration}</span>
            </div>
          )}
          {latestEvent?.stage_num != null && (
            <div className="flex items-center justify-between px-3 py-2">
              <span className="text-muted">Stage</span>
              <span className="text-text/70 tabular-nums">
                {latestEvent.stage_num} of {latestEvent.total_stages}
              </span>
            </div>
          )}
        </div>
      )}

      {/* Active stage */}
      {isActive && (
        <div className="rounded border border-border/40 px-3 py-2.5 space-y-1">
          <p className="text-xs text-accent/70 italic">Running…</p>
          {activeSummary && (
            <p className="text-xs text-muted/60">{activeSummary}</p>
          )}
        </div>
      )}

      {/* Not started yet */}
      {!hasStarted && (
        <div className="rounded border border-border/40 px-3 py-2.5">
          <p className="text-xs text-muted/60 italic">
            This stage has not started yet.
          </p>
        </div>
      )}

      {/* ── Rich stage-specific detail (available after stage completes) ── */}

      {isComplete && (
        <div className="border-t border-border/30 pt-3">
          {selected.stageId === "s1_intake" && (() => {
            const d = resolveDetail(finalStageDetails?.s1_intake);
            return d ? <S1Detail d={d as NonNullable<StageDetails["s1_intake"]>} /> : null;
          })()}
          {selected.stageId === "s2_scope" && (() => {
            const d = resolveDetail(finalStageDetails?.s2_scope);
            return d ? <S2Detail d={d as NonNullable<StageDetails["s2_scope"]>} /> : null;
          })()}
          {selected.stageId === "s3_plan_search" && (() => {
            const d = resolveDetail(finalStageDetails?.s3_plan_search);
            return d ? <S3Detail d={d as NonNullable<StageDetails["s3_plan_search"]>} /> : null;
          })()}
          {selected.stageId === "search_execution" && (() => {
            const d = resolveDetail(finalStageDetails?.search_execution);
            return d ? <SearchDetail d={d as NonNullable<StageDetails["search_execution"]>} /> : null;
          })()}
          {selected.stageId === "s4_source_quality" && (() => {
            const d = resolveDetail(finalStageDetails?.s4_source_quality);
            return d ? <S4Detail d={d as NonNullable<StageDetails["s4_source_quality"]>} /> : null;
          })()}
          {selected.stageId === "s5_perspectives" && (() => {
            const d = resolveDetail(finalStageDetails?.s5_perspectives);
            return d ? <S5Detail d={d as NonNullable<StageDetails["s5_perspectives"]>} /> : null;
          })()}
          {selected.stageId === "s6_verification" && (() => {
            const d = resolveDetail(finalStageDetails?.s6_verification);
            return d ? <S6Detail d={d as NonNullable<StageDetails["s6_verification"]>} /> : null;
          })()}
          {selected.stageId === "s7_compose_check" && (() => {
            const d = resolveDetail(finalStageDetails?.s7_compose_check);
            return d ? (
              <S7Detail
                d={d as NonNullable<StageDetails["s7_compose_check"]>}
                neutrality={msg.result?.neutrality ?? null}
              />
            ) : null;
          })()}

          {/* Fallback when no detail is available for this stage */}
          {!resolveDetail(finalStageDetails?.[selected.stageId as keyof StageDetails]) && (
            <div className="rounded border border-border/40 px-3 py-2.5">
              <p className="text-xs text-muted/60">
                No structured details were emitted for this stage.
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
