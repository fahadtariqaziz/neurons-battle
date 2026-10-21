"""Request and response models of the HTTP API.

FastAPI validates every request body against these BEFORE our code runs: a malformed body gets a
422 with a clear message, and the Swagger page (/docs) shows each model with its fields.

The resume body is a "discriminated union": the `type` field says which pause you are answering,
and FastAPI picks the matching model (ClarificationResume, RedFlagResume, ...) to validate the rest.
"""

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from ai_decision_arena.nodes.intake import MAX_CONTEXT_CHARS, MAX_QUESTION_CHARS, MIN_QUESTION_CHARS
from ai_decision_arena.schemas import Evidence, FinalReport, HumanReviewInput

# What the HTTP layer knows about a session (separate from the graph's own `status` field):
# running     a background run is working on it right now
# paused      waiting for the user (see `pending`)
# interrupted the run stopped mid-way (server restart, crash); POST /resume {"type": "continue"} picks it up
# finished    the graph reached END (completed, stopped_by_user or failed: see workflow_status)
RunState = Literal["running", "paused", "interrupted", "finished"]
PauseType = Literal["clarification", "red_flag", "human_review"]


# --- requests ----------------------------------------------------------------------------------

class CreateDecisionRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)   # "   " counts as empty, like in intake

    question: str = Field(min_length=MIN_QUESTION_CHARS, max_length=MAX_QUESTION_CHARS,
                          examples=["I have type 2 diabetes"])
    context: str = Field(default="", max_length=MAX_CONTEXT_CHARS, description="Optional extra context.")


class ClarificationResume(BaseModel):
    type: Literal["clarification"]
    answers: dict[str, str] = Field(description="question -> answer, using the exact question texts from `pending`. "
                                                "Leave a question out (or answer \"\") to skip it.")


class RedFlagResume(BaseModel):
    type: Literal["red_flag"]
    action: Literal["continue", "stop"]


class HumanReviewResume(HumanReviewInput):
    """Same fields as the graph's HumanReviewInput (action, feedback, selected_plan_id, profile_changes)."""

    type: Literal["human_review"]


class ContinueResume(BaseModel):
    """Restart an interrupted run from its last checkpoint (like run_graph.py --resume)."""

    type: Literal["continue"]


ResumeRequest = Annotated[
    ClarificationResume | RedFlagResume | HumanReviewResume | ContinueResume,
    Field(discriminator="type"),
]


# --- responses ---------------------------------------------------------------------------------

class Accepted(BaseModel):
    thread_id: str
    run_state: RunState = "running"
    message: str = "Accepted. Poll GET /api/decisions/{thread_id} for progress."


class ProgressLine(BaseModel):
    at: str
    node: str
    message: str


class PendingPause(BaseModel):
    type: PauseType
    payload: dict[str, Any] = Field(description="Exactly what the graph's interrupt() sent: questions, red flags "
                                                "or the review summary. Includes `error` if the last reply was refused.")


class ErrorInfo(BaseModel):
    code: str
    message: str


class DecisionStatus(BaseModel):
    thread_id: str
    run_state: RunState
    workflow_status: str | None = Field(description="The graph's own status (intake, researching, completed, ...).")
    question: str | None = None
    condition_name: str | None = None
    red_flags: list[str] = Field(default_factory=list)
    pending: PendingPause | None = None
    progress: list[ProgressLine] = Field(default_factory=list,
                                         description="Live progress of THIS server process (lost on restart).")
    error: ErrorInfo | None = Field(default=None, description="The graph's stored error, or a crash of the background run.")
    has_report: bool = False


class ReportResponse(BaseModel):
    thread_id: str
    workflow_status: str
    report: FinalReport


class EvidenceResponse(BaseModel):
    thread_id: str
    count: int
    verification_counts: dict[str, int] = Field(description="verification_status -> number of evidence items")
    evidence: list[Evidence]


class ErrorResponse(BaseModel):
    """Every error the API returns has this shape: {"error": {"code": ..., "message": ...}}."""

    error: ErrorInfo
