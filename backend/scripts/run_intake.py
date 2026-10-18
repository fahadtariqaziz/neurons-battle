"""Step 3.1 — run the Intake node on a question.

Run from the backend/ folder:
    uv run python scripts/run_intake.py
    uv run python scripts/run_intake.py "We have a Django monolith on AWS and 5 devs. Should we move to microservices?"
"""

import json
import sys

from langgraph.graph import END, START, StateGraph

from ai_decision_arena.nodes.intake import InvalidInputError, intake_node
from ai_decision_arena.state import ArenaState

question = " ".join(sys.argv[1:]) or (
    "I am building an AI application that may have 10,000 users. "
    "Should I use PostgreSQL or MongoDB for the backend?"
)

# A one-node graph for now; the full graph comes later.
builder = StateGraph(ArenaState)
builder.add_node("intake", intake_node)
builder.add_edge(START, "intake")
builder.add_edge("intake", END)
graph = builder.compile()

try:
    result = graph.invoke(
        {"question": question},
        config={"run_name": "intake_demo", "metadata": {"step": "3.1"}},
    )
except InvalidInputError as exc:
    # Expected rejection (bad input): show a clean message instead of a traceback.
    sys.exit(f"❌ Rejected: {exc}")
print(json.dumps(result, indent=2))
