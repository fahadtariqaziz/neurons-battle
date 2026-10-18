"""Step 4.2 — run ONLY the Research node on a saved, already-clarified state (no questions).

Run from the backend/ folder:
    uv run python scripts/run_research.py
"""

from langgraph.graph import END, START, StateGraph

from ai_decision_arena.nodes.research import research_node
from ai_decision_arena.state import ArenaState
from print_helpers import print_research
from demo_data import CLARIFIED_STATE

builder = StateGraph(ArenaState)
builder.add_node("research", research_node)
builder.add_edge(START, "research")
builder.add_edge("research", END)
graph = builder.compile()

print("🔎 Researching (planner → Tavily → evidence extractor). Usually takes about 1 minute...")
result = graph.invoke(CLARIFIED_STATE, config={"run_name": "research_demo", "metadata": {"step": "4.2"}})
print_research(result)
