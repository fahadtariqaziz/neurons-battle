"""The AI Decision Arena graph. Grows one node at a time as each phase is built.

Current flow (Phase 4):
    START → intake → clarification ─┬─(need_clarification)─► await_clarification ─► clarification (loop)
                                    └─(enough info)────────► research → END   (debate comes in Phase 5)
"""

from typing import Literal

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph

from ai_decision_arena.nodes.clarification import await_clarification_node, clarification_node
from ai_decision_arena.nodes.intake import intake_node
from ai_decision_arena.nodes.research import research_node
from ai_decision_arena.state import ArenaState


# --- routing functions: read the state, return the NAME of the next step ------------

def route_after_clarification(state: ArenaState) -> Literal["await_clarification", "research"]:
    return "await_clarification" if state.get("need_clarification") else "research"


# --- graph ----------------------------------------------------------------------------

def build_graph(checkpointer: BaseCheckpointSaver | None = None):
    """A checkpointer is required for interrupt()/resume. Phase 3 uses InMemorySaver,
    Phase 7 switches to PostgreSQL."""
    builder = StateGraph(ArenaState)

    builder.add_node("intake", intake_node)
    builder.add_node("clarification", clarification_node)
    builder.add_node("await_clarification", await_clarification_node)
    builder.add_node("research", research_node)

    builder.add_edge(START, "intake")
    builder.add_edge("intake", "clarification")
    builder.add_conditional_edges(
        "clarification",
        route_after_clarification,
        {"await_clarification": "await_clarification", "research": "research"},
    )
    builder.add_edge("await_clarification", "clarification")   # re-evaluate after answers
    builder.add_edge("research", END)                            # Proposer comes in Phase 5

    return builder.compile(checkpointer=checkpointer)
