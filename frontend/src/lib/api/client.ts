// The only place that talks to the backend. UI components call these functions and never use fetch directly.
//
// Every backend error looks like {"error": {"code", "message"}}; it is thrown as an ApiError so the UI
// can show the message and decide by status / code (e.g. 409 "already_running").

import type {
  Accepted,
  CreateDecisionRequest,
  DecisionStatus,
  EvidenceResponse,
  LiveSnapshot,
  ReportResponse,
  ResumeRequest,
  SessionList,
} from "./types";

// NEXT_PUBLIC_ variables are copied into the browser bundle: only put public values here, never API keys.
const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const BASE = `${API_URL}/api/decisions`;

export class ApiError extends Error {
  constructor(
    public status: number, // HTTP status; 0 = the backend could not be reached
    public code: string,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${BASE}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...init?.headers },
      cache: "no-store", // status changes every few seconds: never reuse an old answer
    });
  } catch {
    throw new ApiError(0, "network_error", `Cannot reach the backend at ${API_URL}. Is it running?`);
  }

  const body = await response.json().catch(() => null);
  if (!response.ok) {
    const error = body?.error;
    throw new ApiError(
      response.status,
      error?.code ?? "http_error",
      error?.message ?? `Request failed with status ${response.status}.`,
    );
  }
  return body as T;
}

/** Start a session. Returns at once (202) with the thread_id; the graph runs in the background. */
export function createDecision(body: CreateDecisionRequest): Promise<Accepted> {
  return request("", { method: "POST", body: JSON.stringify(body) });
}

/** Current state of a session: run_state, progress lines, pending pause. Poll this. */
export function getDecision(threadId: string): Promise<DecisionStatus> {
  return request(`/${encodeURIComponent(threadId)}`);
}

/** Answer the pending pause (or {type: "continue"} for an interrupted run). */
export function resumeDecision(threadId: string, body: ResumeRequest): Promise<Accepted> {
  return request(`/${encodeURIComponent(threadId)}/resume`, { method: "POST", body: JSON.stringify(body) });
}

/** The final report. 409 "not_finished" until the session is finished. */
export function getReport(threadId: string): Promise<ReportResponse> {
  return request(`/${encodeURIComponent(threadId)}/report`);
}

/** Evidence kept so far, with verification status. */
export function getEvidence(threadId: string): Promise<EvidenceResponse> {
  return request(`/${encodeURIComponent(threadId)}/evidence`);
}

/** Everything the agents produced so far: case facts, evidence counts, plans, criticisms, scores, verdicts. */
export function getLive(threadId: string): Promise<LiveSnapshot> {
  return request(`/${encodeURIComponent(threadId)}/live`);
}

/** Recent sessions, newest first (503 if the database cannot be read). */
export function listDecisions(limit = 20): Promise<SessionList> {
  return request(`?limit=${limit}`);
}
