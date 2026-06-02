// ── SSE / API wire types ──────────────────────────────────────────────────────

export type MicroEventKind =
  | "summary"
  | "source"
  | "perspective"
  | "verification"
  | "neutrality"
  | "warning";

export interface AuditMicroEvent {
  id: string;
  text: string;
  kind?: MicroEventKind;
  detail?: Record<string, unknown>;
}

export interface ProgressEvent {
  stage_id: string;
  stage_num: number | null;
  total_stages: number;
  status: "started" | "completed" | "stopped";
  label: string;
  duration_ms: number | null;
  /** Content-conditioned one-line summary from completed stage output. */
  summary?: string;
  /** Audit micro-events derived from completed stage output. */
  micro_events?: AuditMicroEvent[];
  /** Compact per-stage detail for the inspector, available during streaming. */
  detail?: Record<string, unknown>;
}

export interface Citation {
  label: string;
  url: string;
  used_for_claim: string;
}

export interface NeutralityCheck {
  avoided_unsolicited_opinion: boolean;
  factually_accurate_and_comprehensive: boolean;
  steelmanned_each_perspective: boolean;
  neutral_terminology_used: boolean;
  equal_depth_across_perspectives: boolean;
  respectful_tone: boolean;
  /** Optional: absent in old localStorage messages; present from Phase 3 onwards. */
  evidence_proportional_to_sources?: boolean;
  revisions_made: string[];
}

// ── Stage details (compact per-stage output from the backend) ─────────────────

export interface StageDetails {
  s1_intake?: {
    canonical_query: string | null;
    modality: string | null;
    notes: string | null;
  };
  s2_scope?: {
    in_scope: boolean | null;
    confidence: number | null;
    reasoning: string | null;
    matched_charter_categories: string[];
    suggested_redirect: string | null;
  };
  s3_plan_search?: {
    needs_search: boolean | null;
    rationale: string | null;
    queries: string[];
    target_source_types: string[];
    why_model_knowledge_insufficient: string | null;
  };
  search_execution?: {
    queries_run: number | null;
    raw_hits: number | null;
    unique_hits: number | null;
    hits_passed: number | null;
    results_capped: boolean | null;
    domains: string[];
  };
  s4_source_quality?: {
    confidence_in_evidence: number | null;
    gaps: string[];
    conflicting_claims: string[];
    sources: Array<{
      domain: string;
      source_type: string | null;
      slant: string | null;
      relevance: number | null;
      confidence: number | null;
    }>;
    sufficiency?: {
      restricted_empirical_claims_required: boolean;
      primary_sources_missing: boolean;
      requested_source_types_missing: string[];
      perspective_coverage_asymmetric: boolean;
      confidence_in_evidence: number | null;
      reasons: string[];
    } | null;
  };
  s5_perspectives?: {
    perspectives: Array<{
      label: string | null;
      core_claims: string[];
      strongest_evidence: string[];
      concerns: string[];
      evidence_coverage?: string | null;
      unsupported_empirical_claims?: string[];
    }>;
    areas_of_consensus: string[];
    areas_of_disagreement: string[];
    empirical_vs_normative: Array<{ claim: string; kind: string }>;
  };
  s6_verification?: {
    overall_calibration_note: string | null;
    things_i_should_not_assert: string[];
    factual_claims: Array<{
      claim: string | null;
      confidence: number | null;
      verification_basis: string | null;
      suggested_hedging: string | null;
      drop_if_uncorroborated: boolean;
      claim_type?: string | null;
      support_level?: string | null;
      attribution?: string | null;
      outcome_relevance?: string | null;
    }>;
  };
  s7_compose_check?: {
    revisions_made: string[];
    residual_uncertainty: string | null;
    suggested_followups: string[];
  };
}

export interface CompletePayload {
  in_scope: boolean;
  answer: string;
  citations: Citation[];
  neutrality: NeutralityCheck | null;
  residual_uncertainty: string | null;
  suggested_followups: string[];
  stage_details?: StageDetails;
}

export interface RunOptions {
  fast_mode: boolean;
  no_search: boolean;
  max_hits: number;
}

// ── Message types (source of truth for UI state) ──────────────────────────────

export interface UserMessage {
  id: string;
  role: "user";
  content: string;
}

export interface AssistantMessage {
  id: string;
  role: "assistant";
  /** "running" while the pipeline is active; "done" on success; "error" on failure. */
  status: "running" | "done" | "error";
  /** Grows as SSE progress events arrive during streaming. */
  traceEvents: ProgressEvent[];
  /** Populated from the SSE complete event. */
  result?: CompletePayload;
  /** Populated from SSE error events or caught exceptions. */
  error?: string;
  /** "interrupted" = local page-close/refresh; "api" = actual backend/network error. */
  errorKind?: "interrupted" | "api";
}

export type ChatMessage = UserMessage | AssistantMessage;

// ── Chat session (localStorage persistence) ───────────────────────────────────

export interface ChatSession {
  id: string;
  title: string;
  createdAt: number;
  updatedAt: number;
  messages: ChatMessage[];
}

// ── Inspector selection ───────────────────────────────────────────────────────

export interface SelectedStage {
  messageId: string;
  stageId: string;
}

// ── Type guards ───────────────────────────────────────────────────────────────

export function isUser(m: ChatMessage): m is UserMessage {
  return m.role === "user";
}

export function isAssistant(m: ChatMessage): m is AssistantMessage {
  return m.role === "assistant";
}
