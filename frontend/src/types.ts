export type Lifecycle =
  | "PROCESSING"
  | "AWAITING_CLARIFICATION"
  | "AWAITING_REVIEW"
  | "REVIEWED"
  | "ERROR_NEEDS_REVIEW";
export interface Proposal {
  document_id: string;
  submitted_on: string;
  proposal_text: string;
}
export interface Evidence {
  document_id: string;
  section: string;
  quote: string;
  start: number;
  end: number;
}
export interface Fact {
  value: string | null;
  state: string;
  evidence: Evidence[];
}
export interface Rule {
  rule_id: string;
  status: "PASS" | "FLAG" | "UNKNOWN";
  explanation: string;
  field_refs: string[];
  calculation: string | null;
  clarification: string | null;
}
export interface AgentRun {
  agent: string;
  execution: string;
  model_calls: number;
  tool_calls: unknown[];
  usage: Record<string, number>;
  output: unknown;
}
export interface Packet {
  run_id: string;
  mode: string;
  workflow_status: string;
  normalized_source: string;
  summary: string;
  rules: Rule[];
  terms: Record<string, Fact>;
  clarification_questions: string[];
  next_actions: string[];
  model_calls: number;
  elapsed_ms: number;
  agent_runs: AgentRun[];
  limitations: string[];
}
export interface Audit {
  action_id: string;
  action: string;
  actor: string;
  note: string;
  submitted_at: string;
  resulting_revision: number;
}
export interface SavedReview {
  review_id: string;
  revision: number;
  lifecycle_status: Lifecycle;
  current_request: Proposal;
  packet: Packet | null;
  pending_interrupt: { reviewer_request?: string; questions?: string[] } | null;
  revision_history: { revision: number }[];
  actions: Audit[];
  reviewed_by: string | null;
  last_error: { message?: string; stage?: string } | null;
}
export interface Summary {
  review_id: string;
  document_id: string;
  revision: number;
  lifecycle_status: Lifecycle;
  updated_at: string;
}
export interface Revision {
  revision: number;
  request: Proposal;
  packet: Packet;
}
export type ActionKind =
  "clarify" | "request_revision" | "mark_reviewed" | "retry";
export interface ActionBody {
  action_id: string;
  expected_revision: number;
  actor: string;
  note: string;
  action?: Exclude<ActionKind, "retry">;
  replacement_proposal_text?: string;
}
