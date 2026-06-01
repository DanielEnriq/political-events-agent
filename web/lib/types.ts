export interface ProgressEvent {
  stage_id: string;
  stage_num: number | null;
  total_stages: number;
  status: "started" | "completed" | "stopped";
  label: string;
  duration_ms: number | null;
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
  revisions_made: string[];
}

export interface CompletePayload {
  in_scope: boolean;
  answer: string;
  citations: Citation[];
  neutrality: NeutralityCheck | null;
  residual_uncertainty: string | null;
  suggested_followups: string[];
}

export interface RunOptions {
  fast_mode: boolean;
  no_search: boolean;
  max_hits: number;
}

export type MessageRole = "user" | "assistant";

export interface ChatMessage {
  role: MessageRole;
  content: string;
  /** Only present on assistant messages that have completed. */
  result?: CompletePayload;
}
