"""FastAPI backend: the same flow as scripts/run_graph.py, over HTTP (for the Next.js frontend).

Run from the backend/ folder:
    uv run uvicorn ai_decision_arena.api.main:app --port 8000
Then open http://localhost:8000/docs (Swagger UI: try every endpoint from the browser).

Flow:
    POST /api/decisions                   → 202 {thread_id}; the graph runs in the background
    GET  /api/decisions/{id}              → poll every ~2 s: run_state, progress lines, pending pause
    POST /api/decisions/{id}/resume       → answer the pending pause (or "continue" an interrupted run)
    GET  /api/decisions/{id}/report       → the final report, once finished
    GET  /api/decisions/{id}/evidence     → kept evidence with verification status

Status and pending pause are read from the checkpoint (graph.get_state), so they survive a restart.
"""

import logging
import uuid
from contextlib import asynccontextmanager
from collections import Counter

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.types import Command
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from starlette.exceptions import HTTPException as StarletteHTTPException

from ai_decision_arena.api.runner import GraphRunner, graph_config
from ai_decision_arena.api.schemas import (
    Accepted,
    ClarificationResume,
    ContinueResume,
    CreateDecisionRequest,
    DecisionStatus,
    ErrorResponse,
    EvidenceResponse,
    HumanReviewResume,
    PendingPause,
    ReportResponse,
    ResumeRequest,
)
from ai_decision_arena.config import get_settings
from ai_decision_arena.db.repository import save_session_status
from ai_decision_arena.graph import build_graph

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


# --- startup / shutdown ------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Runs once at startup (before `yield`) and once at shutdown (after it).
    A connection POOL instead of 7.2's single connection: several requests and background runs use the
    checkpointer at the same time, and one psycopg connection must not be shared between threads."""
    pool = ConnectionPool(
        get_settings().database_url,
        min_size=1,
        max_size=10,
        # What PostgresSaver needs from every connection (same as PostgresSaver.from_conn_string sets up).
        kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
        open=True,
    )
    saver = PostgresSaver(pool)
    saver.setup()                                   # creates LangGraph's tables if missing (safe every time)
    graph = build_graph(checkpointer=saver)
    app.state.graph = graph
    app.state.runner = GraphRunner(graph)
    yield
    pool.close()


app = FastAPI(
    title="Health Decision Arena API",
    version="0.8.0",
    description="Start a session, answer its pauses, read the report. Health information only, not medical advice.",
    lifespan=lifespan,
    responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
)
# The Next.js dev server (Phase 9) runs on another port, so the browser needs CORS permission.
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:3000"], allow_methods=["*"], allow_headers=["*"])


# --- errors: always {"error": {"code", "message"}} ---------------------------------------------

class ApiError(Exception):
    def __init__(self, status_code: int, code: str, message: str):
        self.status_code, self.code, self.message = status_code, code, message


def _error(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"error": {"code": code, "message": message}})


@app.exception_handler(ApiError)
async def api_error_handler(request: Request, exc: ApiError):
    return _error(exc.status_code, exc.code, exc.message)


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    """FastAPI's own 422 (bad body) in our error shape. Message like "body.action: Input should be ..."."""
    parts = [f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()[:3]]
    return _error(422, "invalid_input", "; ".join(parts))


@app.exception_handler(StarletteHTTPException)
async def http_error_handler(request: Request, exc: StarletteHTTPException):
    """E.g. a URL that does not exist (404) or a wrong method (405)."""
    return _error(exc.status_code, "http_error", str(exc.detail))


# --- helpers -----------------------------------------------------------------------------------

def _snapshot(request: Request, thread_id: str):
    """The latest checkpoint of a session; 404 if there is none and no run is starting it."""
    snapshot = request.app.state.graph.get_state(graph_config(thread_id))
    if not snapshot.values and not request.app.state.runner.is_running(thread_id):
        raise ApiError(404, "not_found", f"No session with thread_id {thread_id}.")
    return snapshot


def _run_state(runner: GraphRunner, thread_id: str, snapshot) -> str:
    if runner.is_running(thread_id):
        return "running"
    if snapshot.interrupts:
        return "paused"
    if snapshot.next:              # nodes still to run, but nobody is running them: restart or crash
        return "interrupted"
    return "finished"


def _start(runner: GraphRunner, thread_id: str, graph_input) -> None:
    if not runner.start(thread_id, graph_input):
        raise ApiError(409, "already_running", "This session is still running; wait until it pauses or finishes.")


# --- endpoints ---------------------------------------------------------------------------------

@app.post("/api/decisions", status_code=status.HTTP_202_ACCEPTED, response_model=Accepted, tags=["decisions"])
def create_decision(body: CreateDecisionRequest, request: Request):
    """Create a session and start the graph in the background. Returns at once with the thread_id."""
    thread_id = str(uuid.uuid4())
    if get_settings().persist_results:
        save_session_status(thread_id, {"question": body.question}, "intake")
    _start(request.app.state.runner, thread_id, {"question": body.question, "user_context": body.context})
    return Accepted(thread_id=thread_id)


@app.get("/api/decisions/{thread_id}", response_model=DecisionStatus, tags=["decisions"])
def get_decision(thread_id: str, request: Request):
    """Poll this every couple of seconds. When run_state is "paused", `pending` says what to send to /resume."""
    runner: GraphRunner = request.app.state.runner
    snapshot = _snapshot(request, thread_id)
    values = snapshot.values or {}
    run_state = _run_state(runner, thread_id, snapshot)

    pending = None
    if run_state == "paused":
        payload = snapshot.interrupts[0].value
        pending = PendingPause(type=payload["type"], payload=payload)

    error = None
    if runner.crash(thread_id):
        error = {"code": "run_crashed", "message": runner.crash(thread_id)}
    elif values.get("error"):
        err = values["error"]
        error = {"code": err.get("category", "error"), "message": f"{err.get('node', '?')}: {err.get('message', '')}"}

    return DecisionStatus(
        thread_id=thread_id,
        run_state=run_state,
        workflow_status=values.get("status"),
        question=values.get("question"),
        condition_name=values.get("condition_name"),
        red_flags=values.get("red_flags", []),
        pending=pending,
        progress=runner.progress(thread_id),
        error=error,
        has_report=bool(values.get("final_report")),
    )


@app.post("/api/decisions/{thread_id}/resume", status_code=status.HTTP_202_ACCEPTED, response_model=Accepted,
          tags=["decisions"])
def resume_decision(thread_id: str, body: ResumeRequest, request: Request):
    """Answer the pending pause. `type` must match pending.type from GET; {"type": "continue"} restarts an
    interrupted run. The graph continues in the background; poll GET again."""
    runner: GraphRunner = request.app.state.runner
    snapshot = _snapshot(request, thread_id)
    run_state = _run_state(runner, thread_id, snapshot)

    if run_state == "running":
        raise ApiError(409, "already_running", "This session is still running; wait until it pauses or finishes.")
    if isinstance(body, ContinueResume):
        if run_state != "interrupted":
            raise ApiError(409, "not_interrupted", f"Nothing to continue: the session is {run_state}.")
        _start(runner, thread_id, None)            # None = continue from the last checkpoint
        return Accepted(thread_id=thread_id)
    if run_state != "paused":
        raise ApiError(409, "nothing_pending", f"The session is not waiting for input (it is {run_state}).")

    payload = snapshot.interrupts[0].value
    if body.type != payload["type"]:
        raise ApiError(409, "wrong_pause_type", f"The session is waiting for '{payload['type']}', not '{body.type}'.")

    # Checks the graph would also make (it re-asks with an error); doing them here gives a direct 422.
    if isinstance(body, ClarificationResume):
        unknown = sorted(set(body.answers) - set(payload["questions"]))
        if unknown:
            raise ApiError(422, "invalid_input", f"Answers for questions that were not asked: {unknown}")
    if isinstance(body, HumanReviewResume) and body.action == "select_plan":
        allowed = payload.get("selectable_plan_ids", [])
        if body.selected_plan_id not in allowed:
            raise ApiError(422, "invalid_input", f"selected_plan_id must be one of {allowed}.")

    reply = body.model_dump(exclude={"type"})      # exactly what interrupt() returns inside the node
    _start(runner, thread_id, Command(resume=reply))
    return Accepted(thread_id=thread_id)


@app.get("/api/decisions/{thread_id}/report", response_model=ReportResponse, tags=["decisions"])
def get_report(thread_id: str, request: Request):
    snapshot = _snapshot(request, thread_id)
    run_state = _run_state(request.app.state.runner, thread_id, snapshot)
    if run_state != "finished":
        raise ApiError(409, "not_finished", f"Not finished yet (the session is {run_state}).")
    values = snapshot.values
    if not values.get("final_report"):
        raise ApiError(409, "no_report", f"This session ended without a report (status {values.get('status')}).")
    return ReportResponse(thread_id=thread_id, workflow_status=values.get("status"), report=values["final_report"])


@app.get("/api/decisions/{thread_id}/evidence", response_model=EvidenceResponse, tags=["decisions"])
def get_evidence(thread_id: str, request: Request):
    """Evidence kept so far (also while running). verification_status stays "pending" until the Evidence Checker ran."""
    evidence = (_snapshot(request, thread_id).values or {}).get("evidence", [])
    counts = Counter(e.get("verification_status", "pending") for e in evidence)
    return EvidenceResponse(thread_id=thread_id, count=len(evidence), verification_counts=dict(counts), evidence=evidence)
