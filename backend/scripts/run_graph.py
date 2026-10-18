"""Run the full graph built so far, with real pause/resume for clarification questions.

Run from the backend/ folder:
    uv run python scripts/run_graph.py
    uv run python scripts/run_graph.py "Should we use Kafka or RabbitMQ for order events?"
"""

import sys
import uuid

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from ai_decision_arena.graph import build_graph
from ai_decision_arena.nodes.intake import InvalidInputError
from print_helpers import print_research

question = " ".join(sys.argv[1:]) or (
    "I am building an AI application that may have 10,000 users. "
    "Should I use PostgreSQL or MongoDB for the backend?"
)

# The checkpointer saves state after every step; that's what makes pausing possible.
# InMemorySaver forgets everything when this script exits (PostgreSQL comes in Phase 7).
graph = build_graph(checkpointer=InMemorySaver())
print(graph.get_graph().draw_ascii())

# One thread_id = one decision session. Resuming needs the SAME thread_id.
thread_id = str(uuid.uuid4())
config = {
    "configurable": {"thread_id": thread_id},
    "run_name": "arena_graph",
    "metadata": {"thread_id": thread_id},   # LangSmith groups runs by thread_id
}
print(f"thread_id: {thread_id}\n")

try:
    result = graph.invoke({"question": question}, config)
except InvalidInputError as exc:
    sys.exit(f"❌ Rejected: {exc}")

# While the graph is paused, the result contains "__interrupt__".
while "__interrupt__" in result:
    payload = result["__interrupt__"][0].value
    snapshot = graph.get_state(config)
    print(f"⏸  Paused at node: {snapshot.next}  |  status: {snapshot.values.get('status')}")
    if payload.get("error"):
        print(f"⚠️  {payload['error']}")
    print(f"\n🤔 Clarification round {payload['round']}. Press Enter to skip a question.\n")

    answers = {q: input(f"Q{i}: {q}\n> ") for i, q in enumerate(payload["questions"], start=1)}

    print("\n▶  Resuming. Research usually takes about 1 minute...\n")
    # Resume the SAME thread: the paused node continues, interrupt() returns this value.
    result = graph.invoke(Command(resume={"answers": answers}), config)

print(f"✅ Finished with status: {result['status']}")
print(f"Requirements: {result.get('requirements')}")
print(f"Constraints:  {result.get('constraints')}")
print(f"Assumptions:  {result.get('assumptions')}")
print_research(result)
