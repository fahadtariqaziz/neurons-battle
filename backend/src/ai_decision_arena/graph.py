"""The Health Decision Arena graph: all 11 logical nodes (Phase 6).

    START → intake ─┬─(red flags)──► await_red_flag_ack ─(continue)─► clarification  /  ─(stop)─► completion
                    └─────────────► clarification ─┬─(need_clarification)─► await_clarification ─► clarification (loop)
                                                   ├─(new red flags)──────► await_red_flag_ack ─(continue)─► research
                                                   └─(enough info)────────► research → proposer → critic → judge
    judge ─┬─(request_more_research)──► research          (focused; bounded; never with red flags / over budget)
           ├─(request_clarification)──► clarification
           └─(proceed / insufficient_evidence)──► evidence_checker ─┬─(material gap, loop allowed)─► research
                                                                    └──────────────────────────────► human_review (interrupt)
                                                                    └─(quick mode: no review pause)─► final_report
    human_review ─┬─(approve / select_plan)──► final_report → completion → END
                  ├─(reject / request_debate_round)──► proposer
                  └─(request_more_research / modify_profile / add_context)──► research
    Any node that raises → its error is stored → error_recovery ─(retry, backoff)─► the failed node
                                                                 └─(permanent)─────► completion (status failed)

Every edge is "guarded": if the state carries an error, the graph goes to error_recovery first.

Quick mode (patient chat, state["mode"] == "quick"): same nodes, but no red-flag pause (pending_red_flags is
empty), no loops (quick settings: max 1 debate round, 0 research retries) and no human review pause. Unless
QUICK_DOUBLE_CHECK=true, the two double-check agents are skipped too, to keep onboarding near 30 seconds:
    research → proposer → judge → final_report → completion
"""

from typing import Callable, Literal

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph

from ai_decision_arena.config import get_settings
from ai_decision_arena.nodes.clarification import await_clarification_node, clarification_node
from ai_decision_arena.nodes.critic import critic_node
from ai_decision_arena.nodes.error_recovery import error_recovery_node, recoverable
from ai_decision_arena.nodes.evidence_checker import evidence_checker_node
from ai_decision_arena.nodes.final_report import completion_node, final_report_node
from ai_decision_arena.nodes.human_review import human_review_node
from ai_decision_arena.nodes.intake import intake_node
from ai_decision_arena.nodes.judge import judge_node
from ai_decision_arena.nodes.proposer import proposer_node
from ai_decision_arena.nodes.red_flag_ack import await_red_flag_ack_node, pending_red_flags
from ai_decision_arena.nodes.research import research_node
from ai_decision_arena.state import ArenaState

# Nodes that can fail (wrapped by error recovery) and can therefore be retried.
NODES = {
    "intake": intake_node,
    "await_red_flag_ack": await_red_flag_ack_node,
    "clarification": clarification_node,
    "await_clarification": await_clarification_node,
    "research": research_node,
    "proposer": proposer_node,
    "critic": critic_node,
    "judge": judge_node,
    "evidence_checker": evidence_checker_node,
    "human_review": human_review_node,
    "final_report": final_report_node,
}


# --- routing functions: read the state, return the NAME of the next step ------------

def route_after_intake(state: ArenaState) -> Literal["await_red_flag_ack", "clarification"]:
    # Emergency signs in the very first message → a human decides before we even ask questions.
    return "await_red_flag_ack" if pending_red_flags(state) else "clarification"


def route_after_clarification(state: ArenaState) -> Literal["await_clarification", "await_red_flag_ack", "research"]:
    if state.get("need_clarification"):
        return "await_clarification"
    if pending_red_flags(state):          # answers revealed emergency signs, no decision yet
        return "await_red_flag_ack"
    return "research"


def route_after_red_flag_ack(state: ArenaState) -> Literal["clarification", "research", "completion"]:
    if state.get("red_flag_action") == "stop":
        return "completion"
    return "research" if state.get("red_flag_resume_to") == "research" else "clarification"


def skips_double_check(state: ArenaState) -> bool:
    """Quick sessions skip the Critic and the Evidence Checker unless QUICK_DOUBLE_CHECK=true."""
    return state.get("mode") == "quick" and not get_settings().quick_double_check


def route_after_proposer(state: ArenaState) -> Literal["critic", "judge"]:
    return "judge" if skips_double_check(state) else "critic"


def route_after_judge(state: ArenaState) -> Literal["research", "clarification", "evidence_checker", "final_report"]:
    # The Judge node already applied the loop limits; here we only read its decision.
    decision = (state.get("verdict") or {}).get("decision")
    if decision == "request_more_research":
        return "research"
    if decision == "request_clarification":
        return "clarification"
    # proceed or insufficient_evidence
    return "final_report" if skips_double_check(state) else "evidence_checker"


def route_after_evidence_checker(state: ArenaState) -> Literal["research", "human_review", "final_report"]:
    decision = (state.get("checker_verdict") or {}).get("decision")
    if decision == "request_more_research":
        return "research"
    return "final_report" if state.get("mode") == "quick" else "human_review"


def route_after_human_review(state: ArenaState) -> Literal["final_report", "proposer", "research"]:
    return state.get("human_review_next") or "final_report"


def route_after_error_recovery(state: ArenaState) -> str:
    return state.get("failed_node") if state.get("recovery_action") == "retry" else "completion"


def guarded(route: Callable[[ArenaState], str] | str):
    """A routing function that sends the graph to error_recovery whenever an error is recorded,
    and otherwise follows `route` (a function, or a fixed target name)."""
    def _route(state: ArenaState) -> str:
        if state.get("error"):
            return "error_recovery"
        return route(state) if callable(route) else route
    return _route


# --- graph ----------------------------------------------------------------------------

def build_graph(checkpointer: BaseCheckpointSaver | None = None):
    """A checkpointer is required for interrupt()/resume: PostgresSaver (checkpointing.py) or InMemorySaver for demos."""
    builder = StateGraph(ArenaState)
    for name, fn in NODES.items():
        builder.add_node(name, recoverable(name)(fn))
    builder.add_node("error_recovery", error_recovery_node)   # pure Python, not wrapped
    builder.add_node("completion", completion_node)           # terminal, pure Python, not wrapped

    def connect(src: str, route, targets: list[str]) -> None:
        builder.add_conditional_edges(src, guarded(route), {t: t for t in targets} | {"error_recovery": "error_recovery"})

    builder.add_edge(START, "intake")
    connect("intake", route_after_intake, ["await_red_flag_ack", "clarification"])
    connect("await_red_flag_ack", route_after_red_flag_ack, ["clarification", "research", "completion"])
    connect("clarification", route_after_clarification, ["await_clarification", "await_red_flag_ack", "research"])
    connect("await_clarification", "clarification", ["clarification"])          # re-evaluate after answers
    connect("research", "proposer", ["proposer"])
    connect("proposer", route_after_proposer, ["critic", "judge"])
    connect("critic", "judge", ["judge"])
    connect("judge", route_after_judge, ["research", "clarification", "evidence_checker", "final_report"])
    connect("evidence_checker", route_after_evidence_checker, ["research", "human_review", "final_report"])
    connect("human_review", route_after_human_review, ["final_report", "proposer", "research"])
    connect("final_report", "completion", ["completion"])
    builder.add_conditional_edges("error_recovery", route_after_error_recovery,
                                  {name: name for name in NODES} | {"completion": "completion"})
    builder.add_edge("completion", END)

    return builder.compile(checkpointer=checkpointer)
