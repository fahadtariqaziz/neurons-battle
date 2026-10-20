"""Node 10 — Error Recovery, plus the wrapper that feeds it.

How it works:
- Every node is wrapped with `recoverable(name)`. If the node raises, the wrapper does NOT crash the
  graph: it stores a safe ErrorRecord in state (`error`, `failed_node`) and returns. LangGraph's own
  interrupt exceptions are re-raised untouched (they are control flow, not failures).
- Every outgoing edge in graph.py is "guarded": if `error` is set, the graph goes to error_recovery.
- error_recovery decides: retry the failed node after a backoff (recoverable error, retries left,
  time budget left) or give up (status "failed" → completion). Explicit edges, no catch-all loop.
- The wrapper also accumulates `active_seconds` (time inside nodes, human pauses excluded), which the
  session time budget uses.

Never put API keys or request payloads in ErrorRecord.message: str(exc) of the SDKs we use does not
contain them, and the message is cut at 500 characters.
"""

import functools
import time

import anthropic
from langgraph.errors import GraphBubbleUp

from ai_decision_arena.config import get_settings
from ai_decision_arena.limits import time_budget_left
from ai_decision_arena.llm import LLMOutputError
from ai_decision_arena.nodes.intake import InvalidInputError
from ai_decision_arena.progress import report
from ai_decision_arena.schemas import ErrorRecord
from ai_decision_arena.state import ArenaState


def classify(exc: Exception) -> tuple[str, bool]:
    """(category, recoverable). Permanent failures are never retried."""
    if isinstance(exc, InvalidInputError):
        return "invalid_input", False
    if isinstance(exc, LLMOutputError):
        return "invalid_llm_output", True          # a fresh attempt often succeeds
    if isinstance(exc, anthropic.RateLimitError):
        return "rate_limit", True
    if isinstance(exc, (anthropic.APITimeoutError, anthropic.APIConnectionError)):
        return "timeout", True
    if isinstance(exc, anthropic.APIStatusError):   # 4xx (auth, bad request) are permanent; 5xx transient
        return ("rate_limit" if exc.status_code == 429 else "unknown"), exc.status_code >= 500
    return "unknown", False                          # a bug is not fixed by retrying


def recoverable(name: str):
    """Decorator: turn exceptions into state (ErrorRecord) and measure active time."""
    def decorate(fn):
        @functools.wraps(fn)
        def wrapped(state: ArenaState) -> dict:
            started = time.time()
            try:
                update = dict(fn(state) or {})
            except GraphBubbleUp:                    # interrupt(): control flow, must bubble up
                raise
            except Exception as exc:                 # noqa: BLE001 - this is the recovery boundary
                category, is_recoverable = classify(exc)
                record = ErrorRecord(
                    node=name,
                    operation=type(exc).__name__,
                    category=category,
                    message=str(exc)[:500],
                    retry_count=state.get("error_retry_counts", {}).get(name, 0),
                    recoverable=is_recoverable,
                )
                report(name, f"failed: {category} ({type(exc).__name__})")
                return {
                    "error": record.model_dump(mode="json"),
                    "failed_node": name,
                    "current_node": name,
                    "active_seconds": round(state.get("active_seconds", 0.0) + time.time() - started, 3),
                }
            update["active_seconds"] = round(state.get("active_seconds", 0.0) + time.time() - started, 3)
            if state.get("error"):
                update.setdefault("error", None)     # a successful run clears a stale record
            return update
        return wrapped
    return decorate


def error_recovery_node(state: ArenaState) -> dict:
    settings = get_settings()
    error = dict(state.get("error") or {})
    node = state.get("failed_node", "")
    counts = dict(state.get("error_retry_counts", {}))
    history = list(state.get("error_history", [])) + [error]
    attempts = counts.get(node, 0)

    blocked = []
    if not error.get("recoverable"):
        blocked.append(f"{error.get('category', 'unknown')} errors are not retried")
    if attempts >= settings.max_node_retries:
        blocked.append(f"retry limit ({settings.max_node_retries}) reached")
    if not time_budget_left(state):
        blocked.append("session time budget spent")

    if not blocked:
        delay = settings.error_backoff_base_seconds * (2 ** attempts)   # 1s, 2s, 4s ...
        report("error_recovery", f"{node} failed ({error.get('category')}); retrying in {delay:.0f}s "
                                 f"(retry {attempts + 1}/{settings.max_node_retries})")
        time.sleep(delay)
        counts[node] = attempts + 1
        return {
            "error": None,                       # cleared so the guarded edges route normally again
            "error_retry_counts": counts,
            "error_history": history,
            "recovery_action": "retry",
            "current_node": "error_recovery",
        }

    reason = "; ".join(blocked)
    report("error_recovery", f"{node} failed permanently: {reason}")
    return {
        "error": error | {"message": f"{error.get('message', '')} [not retried: {reason}]"[:500]},
        "error_history": history,
        "recovery_action": "fail",
        "status": "failed",
        "current_node": "error_recovery",
    }
