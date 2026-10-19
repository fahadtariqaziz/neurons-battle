"""The Health Decision Arena graph. Grows one node at a time as each phase is built.

Current flow (Phase 5):
    START → intake ─┬─(red flags)──► await_red_flag_ack ─(continue)─► clarification   /  ─(stop)─► END
                    └─────────────► clarification ─┬─(need_clarification)─► await_clarification ─► clarification (loop)
                                                   ├─(new red flags)──────► await_red_flag_ack ─(continue)─► research  /  ─(stop)─► END
                                                   └─(enough info)────────► research → proposer → critic → judge
    judge ─┬─(request_more_research)──► research          (focused follow-up, bounded; never when red flags)
           ├─(request_clarification)──► clarification     (Judge's questions, bounded)
           └─(proceed / insufficient_evidence)──► evidence_checker   (Phase 6; END for now)
"""

from typing import Literal

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph

from ai_decision_arena.nodes.clarification import await_clarification_node, clarification_node
from ai_decision_arena.nodes.critic import critic_node
from ai_decision_arena.nodes.intake import intake_node
from ai_decision_arena.nodes.judge import judge_node
from ai_decision_arena.nodes.proposer import proposer_node
from ai_decision_arena.nodes.red_flag_ack import await_red_flag_ack_node, pending_red_flags
from ai_decision_arena.nodes.research import research_node
from ai_decision_arena.state import ArenaState


# --- routing functions: read the state, return the NAME of the next step ------------

def route_after_intake(state: ArenaState) -> Literal["await_red_flag_ack", "clarification"]:
    # Emergency signs in the very first message → a human decides before we even ask questions.
    return "await_red_flag_ack" if pending_red_flags(state) else "clarification"


def route_after_clarification(state: ArenaState) -> Literal["await_clarification", "await_red_flag_ack", "research"]:
    if state.get("need_clarification"):
        return "await_clarification"
    if pending_red_flags(state):          # answers revealed emergency signs not yet acknowledged
        return "await_red_flag_ack"
    return "research"


def route_after_red_flag_ack(state: ArenaState) -> Literal["clarification", "research", "end"]:
    if state.get("red_flag_action") == "stop":
        return "end"
    return "research" if state.get("red_flag_resume_to") == "research" else "clarification"


def route_after_judge(state: ArenaState) -> Literal["research", "clarification", "evidence_checker"]:
    # The Judge node already applied the loop limits; here we only read its decision.
    decision = (state.get("verdict") or {}).get("decision")
    if decision == "request_more_research":
        return "research"
    if decision == "request_clarification":
        return "clarification"
    return "evidence_checker"   # proceed or insufficient_evidence


# --- graph ----------------------------------------------------------------------------

def build_graph(checkpointer: BaseCheckpointSaver | None = None):
    """A checkpointer is required for interrupt()/resume. Phase 3 uses InMemorySaver,
    Phase 7 switches to PostgreSQL."""
    builder = StateGraph(ArenaState)

    builder.add_node("intake", intake_node)
    builder.add_node("clarification", clarification_node)
    builder.add_node("await_clarification", await_clarification_node)
    builder.add_node("await_red_flag_ack", await_red_flag_ack_node)
    builder.add_node("research", research_node)
    builder.add_node("proposer", proposer_node)
    builder.add_node("critic", critic_node)
    builder.add_node("judge", judge_node)

    builder.add_edge(START, "intake")
    builder.add_conditional_edges(
        "intake",
        route_after_intake,
        {"await_red_flag_ack": "await_red_flag_ack", "clarification": "clarification"},
    )
    builder.add_conditional_edges(
        "clarification",
        route_after_clarification,
        {"await_clarification": "await_clarification", "await_red_flag_ack": "await_red_flag_ack", "research": "research"},
    )
    builder.add_edge("await_clarification", "clarification")   # re-evaluate after answers
    builder.add_conditional_edges(
        "await_red_flag_ack",
        route_after_red_flag_ack,
        {"clarification": "clarification", "research": "research", "end": END},
    )
    builder.add_edge("research", "proposer")
    builder.add_edge("proposer", "critic")
    builder.add_edge("critic", "judge")
    builder.add_conditional_edges(
        "judge",
        route_after_judge,
        {"research": "research", "clarification": "clarification", "evidence_checker": END},   # checker: Phase 6.1
    )

    return builder.compile(checkpointer=checkpointer)
