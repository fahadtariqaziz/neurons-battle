// TypeScript mirror of the backend's API models (backend/src/ai_decision_arena/api/schemas.py
// and the parts of schemas.py they include). Written by hand: if a backend model changes, change it here too.

// --- session status (GET /api/decisions/{thread_id}) ---------------------------------------------

/** What the HTTP layer knows about a session (not the graph's own status). */
export type RunState = "running" | "paused" | "interrupted" | "finished";

export type PauseType = "clarification" | "red_flag" | "human_review";

export type HumanAction =
  | "approve"
  | "select_plan"
  | "reject"
  | "request_debate_round"
  | "request_more_research"
  | "modify_profile"
  | "add_context";

export interface ProgressLine {
  at: string; // ISO time
  node: string;
  message: string;
}

/** Exactly what the graph's interrupt() sent. `error` is set when the previous reply was refused. */
export interface ClarificationPayload {
  type: "clarification";
  questions: string[];
  round: number;
  error?: string;
}

export interface RedFlagPayload {
  type: "red_flag";
  red_flags: string[];
  resume_to: "clarification" | "research";
  options: ("continue" | "stop")[];
  message: string;
  error?: string;
}

export interface ReviewPerspective {
  perspective: Perspective;
  label: string;
  plan_id: string | null;
  reason?: string; // when there is no plan
  name?: string;
  summary?: string;
  weighted_total?: number | null;
  confidence?: string | null;
  difficulty?: string;
  verification_counts?: Record<string, number>;
  top_objections?: string[];
}

export interface HumanReviewPayload {
  type: "human_review";
  round: number;
  red_flags: string[];
  perspectives: ReviewPerspective[];
  selectable_plan_ids: string[];
  unresolved_questions: string[];
  options: Record<HumanAction, string>; // action -> description
  limits: { can_debate: boolean; can_research: boolean; blocked_by: string[] };
  error?: string;
}

/** `type` tells which payload it is (TypeScript narrows on it: if (p.type === "clarification") ...). */
export type PendingPause =
  | { type: "clarification"; payload: ClarificationPayload }
  | { type: "red_flag"; payload: RedFlagPayload }
  | { type: "human_review"; payload: HumanReviewPayload };

export interface ErrorInfo {
  code: string;
  message: string;
}

export interface DecisionStatus {
  thread_id: string;
  run_state: RunState;
  workflow_status: string | null; // intake, researching, debating, completed, ...
  question: string | null;
  condition_name: string | null;
  red_flags: string[];
  pending: PendingPause | null;
  progress: ProgressLine[]; // lost when the server restarts
  error: ErrorInfo | null;
  has_report: boolean;
}

export interface Accepted {
  thread_id: string;
  run_state: RunState;
  message: string;
}

// --- requests ----------------------------------------------------------------------------------

export interface CreateDecisionRequest {
  question: string;
  context?: string;
}

/** Body of POST /resume. `type` must match pending.type (or "continue" for an interrupted run). */
export type ResumeRequest =
  | { type: "clarification"; answers: Record<string, string> } // exact question text -> answer
  | { type: "red_flag"; action: "continue" | "stop" }
  | {
      type: "human_review";
      action: HumanAction;
      feedback?: string;
      selected_plan_id?: string;
      profile_changes?: Record<string, string>;
    }
  | { type: "continue" };

// --- evidence (GET /evidence) --------------------------------------------------------------------

export type Perspective = "research" | "doctor" | "patient";

export type VerificationStatus =
  | "pending"
  | "verified"
  | "partially_supported"
  | "unsupported"
  | "contradicted"
  | "irrelevant"
  | "unavailable";

export interface Evidence {
  evidence_id: string;
  perspective: Perspective;
  source_title: string;
  source_url: string;
  source_type: string;
  evidence_strength: string;
  published_at: string | null;
  retrieved_at: string;
  relevant_excerpt: string;
  is_direct_quote: boolean;
  claims_supported: string[];
  limitations: string[];
  patient_context: { is_recurring: boolean; experience_described: string } | null;
  sentiment: "positive" | "negative" | "mixed" | "neutral" | null;
  relevance_score: number;
  reliability_notes: string;
  verification_status: VerificationStatus;
}

export interface EvidenceResponse {
  thread_id: string;
  count: number;
  verification_counts: Record<string, number>;
  evidence: Evidence[];
}

// --- final report (GET /report) ------------------------------------------------------------------

export interface CarePlan {
  plan_id: string;
  perspective: Perspective;
  round: number;
  name: string;
  summary: string;
  daily_routine: string[];
  diet: string[];
  medications_treatments: string[];
  expected_timeline: string;
  prevalence_and_outlook: string;
  benefits: string[];
  drawbacks_risks: string[];
  assumptions: string[];
  difficulty: string;
  safety_notes: string;
  supporting_evidence_ids: string[];
  evidence_gaps: string[];
}

export interface PlanScore {
  plan_id: string;
  criterion_scores: { criterion: string; score: number; explanation: string }[];
  weighted_total: number | null;
  key_benefits: string[];
  key_drawbacks: string[];
  confidence: string;
  confidence_reason: string;
  supporting_evidence_ids: string[];
  remaining_risks: string[];
}

export interface PerspectiveResult {
  perspective: Perspective;
  plan: CarePlan | null;
  score: PlanScore | null;
  key_evidence: { evidence_id: string; title: string; url: string; verification_status: VerificationStatus }[];
  critic_key_objections: string[];
  verification_counts: Record<string, number>;
  verification_notes: string[];
  unavailable_reason: string;
  is_user_choice: boolean;
}

export interface FinalReport {
  generated_at: string;
  original_question: string;
  condition_name: string;
  confirmed_profile: Record<string, string>;
  symptoms: Record<string, string>;
  constraints: Record<string, string>;
  clarifications: Record<string, string>;
  assumptions: string[];
  research_methodology: string;
  overview: string;
  perspectives: PerspectiveResult[];
  where_perspectives_agree: string[];
  where_perspectives_differ: string[];
  is_conditional: boolean;
  uncertainties: string[];
  unsupported_claims: string[];
  unresolved_questions: string[];
  next_steps: string[];
  human_action: string | null;
  human_selected_plan_id: string | null;
  red_flags: string[];
  withdrawn_red_flags: string[];
  disclaimer: string;
}

export interface ReportResponse {
  thread_id: string;
  workflow_status: string;
  report: FinalReport;
}
