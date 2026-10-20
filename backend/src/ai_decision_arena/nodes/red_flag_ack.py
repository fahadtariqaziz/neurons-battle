"""Node 2b — Red-flag pause: emergency warning signs need a HUMAN decision before we go on.

Entered from two places (see graph.py):
- right after intake, when the first message already contains an emergency sign
  (no point in asking six questions first), and
- after clarification, when the answers revealed one.

The user replies {"action": "continue"} (go on with the questions / research, for later discussion
with a doctor) or {"action": "stop"} (end now; status "stopped_by_user", nothing else is spent).
The decision is made ONCE per session: after "continue", later red flags (e.g. revealed by more answers
or a Judge-triggered clarification round) are still shown immediately in the UI, but the graph does not
stop again. Tested 2026-10-20: re-pausing for "new" flags asked twice within a minute, partly because the
LLM restated already-acknowledged flags in new words.

No LLM call here: an interrupted node re-runs from line 1 on resume (same rule as await_clarification).
Writes (owner): red_flags_acknowledged, red_flag_action, red_flag_resume_to, status, current_node.
"""

from langgraph.types import interrupt
from pydantic import ValidationError

from ai_decision_arena.schemas import RedFlagResponse
from ai_decision_arena.state import ArenaState


def pending_red_flags(state: ArenaState) -> list[str]:
    """Red flags that still need a human decision: all of them until the user has decided once.
    Withdrawn flags count too (marked as such): once something looked like an emergency, a human decides,
    even if a later answer contradicted it. Withdrawing a flag never skips the pause."""
    if state.get("red_flag_action") == "continue":
        return []
    withdrawn = [f"{w['flag']}  [withdrawn after your answers: {w['reason']}]" for w in state.get("withdrawn_red_flags", [])]
    return list(state.get("red_flags", [])) + withdrawn


def await_red_flag_ack_node(state: ArenaState) -> dict:
    flags = pending_red_flags(state)
    # Where to go after "continue": back into the flow at the point we interrupted it.
    resume_to = "clarification" if state.get("current_node") == "intake" else "research"
    payload = {
        "type": "red_flag",
        "red_flags": flags,
        "resume_to": resume_to,
        "options": ["continue", "stop"],
        "message": "Possible emergency signs were reported. This tool gives information only. "
                   "If any of these is happening now, seek medical care first.",
    }

    error = None
    while True:   # keep asking until the reply is valid; each interrupt() is a separate pause
        raw = interrupt((payload | {"error": error}) if error else payload)
        try:
            response = RedFlagResponse.model_validate(raw)
            break
        except ValidationError as exc:
            error = f"Invalid reply: {exc.errors()[0]['msg']}. Send {{\"action\": \"continue\"}} or {{\"action\": \"stop\"}}."

    update = {
        "red_flags_acknowledged": list(state.get("red_flags", [])),
        "red_flag_action": response.action,
        "red_flag_resume_to": resume_to,
        "current_node": "await_red_flag_ack",
    }
    update["status"] = "stopped_by_user" if response.action == "stop" else (
        "researching" if resume_to == "research" else "intake"
    )
    return update
