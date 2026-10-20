"""Node 8 — Human Review: the user inspects the three winning plans and decides what happens next.

Interrupt node (no LLM): the payload summarises the winners, their scores, verification counts and the
Critic's top objections. The reply is validated with HumanReviewInput; invalid or impossible choices
re-interrupt with an error (while-loop pattern). The LLM never approves on the user's behalf.

Actions and routes (bounded by the loop limits in limits.loops_allowed):
- approve, select_plan            → final_report
- reject (feedback required)      → proposer (new debate round driven by the feedback); if no round is left → final_report
- request_debate_round            → proposer
- request_more_research (say what)→ research (focused)
- modify_profile / add_context    → facts merged, then research if possible, else proposer, else final_report

Writes (owner): human_action, user_feedback, human_review_round_count, human_review_next,
human_selected_plan_id, health_profile / user_context (when changed), research_focus,
research_retry_count (when looping), status, current_node.
"""

from langgraph.types import interrupt
from pydantic import ValidationError

from ai_decision_arena.limits import loops_allowed
from ai_decision_arena.schemas import PERSPECTIVES, PERSPECTIVE_LABELS, HumanReviewInput
from ai_decision_arena.state import ArenaState

ACTIONS = {
    "approve": "Accept the three plans and write the final report.",
    "select_plan": "Mark the one plan you want to follow up on, then write the report.",
    "reject": "Reject the plans and say why; a new debate round uses your feedback.",
    "request_debate_round": "Run another proposer → critic → judge round.",
    "request_more_research": "Search for something specific (say what).",
    "modify_profile": "Correct a fact about you (key: value) and re-check.",
    "add_context": "Add context that was missing and re-check.",
}


def _winner_summary(state: ArenaState, perspective: str) -> dict:
    verdict = state.get("verdict") or {}
    plan_id = verdict.get("winning_plan_ids", {}).get(perspective)
    base = {"perspective": perspective, "label": PERSPECTIVE_LABELS[perspective], "plan_id": plan_id}
    if not plan_id:
        return base | {"reason": (state.get("proposer_notes") or {}).get(perspective, "No defensible plan.")}
    plan = next(p for p in state.get("care_plans", []) if p["plan_id"] == plan_id)
    score = next((s for s in state.get("scores", []) if s["plan_id"] == plan_id), {})
    crit = next((c for c in state.get("criticisms", []) if c["plan_id"] == plan_id), {"points": []})
    counts: dict[str, int] = {}
    for v in state.get("verification_results", []):
        if v["plan_id"] == plan_id:
            counts[v["status"]] = counts.get(v["status"], 0) + 1
    return base | {
        "name": plan["name"],
        "summary": plan["summary"],
        "weighted_total": score.get("weighted_total"),
        "confidence": score.get("confidence"),
        "difficulty": plan["difficulty"],
        "verification_counts": counts,
        "top_objections": [f"[{p['severity']}] {p['issue']}" for p in crit["points"][:2]],
    }


def _payload(state: ArenaState) -> dict:
    can_debate, can_research, _, blocked = loops_allowed(state)
    return {
        "type": "human_review",
        "round": state.get("human_review_round_count", 0) + 1,
        "red_flags": state.get("red_flags", []),
        "perspectives": [_winner_summary(state, p) for p in PERSPECTIVES],
        "all_plan_ids": [p["plan_id"] for p in state.get("care_plans", [])],
        "unresolved_questions": state.get("unresolved_questions", []),
        "options": ACTIONS,
        "limits": {"can_debate": can_debate, "can_research": can_research, "blocked_by": blocked},
    }


def _apply(state: ArenaState, review: HumanReviewInput) -> tuple[str | None, dict]:
    """Validate the choice against the state and limits. Returns (error, update)."""
    can_debate, can_research, _, blocked = loops_allowed(state)
    plan_ids = {p["plan_id"] for p in state.get("care_plans", [])}
    feedback = review.feedback.strip()
    update: dict = {
        "human_action": review.action,
        "user_feedback": feedback,
        "human_review_round_count": state.get("human_review_round_count", 0) + 1,
        "current_node": "human_review",
    }
    limit_note = f" ({'; '.join(blocked)})" if blocked else ""

    if review.action == "approve":
        return None, update | {"human_review_next": "final_report", "status": "reporting"}

    if review.action == "select_plan":
        if review.selected_plan_id not in plan_ids:
            return f"selected_plan_id must be one of {sorted(plan_ids)}.", {}
        return None, update | {"human_selected_plan_id": review.selected_plan_id,
                               "human_review_next": "final_report", "status": "reporting"}

    if review.action == "reject":
        if not feedback:
            return "Please say what is wrong with the plans (feedback) so the next round can address it.", {}
        if can_debate:
            return None, update | {"human_review_next": "proposer", "status": "debating"}
        return None, update | {"human_review_next": "final_report", "status": "reporting"}   # bounded: report records the rejection

    if review.action == "request_debate_round":
        if not can_debate:
            return f"No debate round left{limit_note}. Choose approve, select_plan or reject.", {}
        return None, update | {"human_review_next": "proposer", "status": "debating"}

    if review.action == "request_more_research":
        if not can_research:
            return f"No research pass left{limit_note}. Choose approve, select_plan, reject or request_debate_round.", {}
        focus = [feedback] if feedback else list(state.get("unresolved_questions", []))
        return None, update | {"human_review_next": "research", "research_focus": focus or ["Re-check the winning plans' weakest claims."],
                               "research_retry_count": state.get("research_retry_count", 0) + 1, "status": "researching"}

    # modify_profile / add_context: merge the new facts, then re-check as far as the limits allow.
    changes: dict = {}
    if review.action == "modify_profile":
        if not review.profile_changes:
            return "profile_changes must contain at least one key: value pair, e.g. {\"age\": \"50\"}.", {}
        changes["health_profile"] = {**state.get("health_profile", {}), **review.profile_changes}
        what = ", ".join(f"{k} = {v}" for k, v in review.profile_changes.items())
    else:
        if not feedback:
            return "Please provide the context to add (feedback).", {}
        changes["user_context"] = (state.get("user_context", "") + "\n" + feedback).strip()
        what = feedback
    if can_research:
        return None, update | changes | {"human_review_next": "research",
                                         "research_focus": [f"The user changed their information: {what}. Re-check what this changes."],
                                         "research_retry_count": state.get("research_retry_count", 0) + 1, "status": "researching"}
    if can_debate:
        return None, update | changes | {"human_review_next": "proposer", "status": "debating"}
    return f"Cannot re-check anymore{limit_note}; the change is recorded. Choose approve, select_plan or reject.", {}


def human_review_node(state: ArenaState) -> dict:
    payload = _payload(state)
    error = None
    while True:
        raw = interrupt((payload | {"error": error}) if error else payload)
        try:
            review = HumanReviewInput.model_validate(raw)
        except ValidationError as exc:
            error = f"Invalid reply: {exc.errors()[0]['msg']} (field: {'.'.join(map(str, exc.errors()[0]['loc']))})"
            continue
        error, update = _apply(state, review)
        if error:
            continue
        return update
