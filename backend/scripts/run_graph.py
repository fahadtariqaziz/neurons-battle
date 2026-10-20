"""Run the full graph built so far, with real pause/resume for clarification questions.

Run from the backend/ folder:
    uv run python scripts/run_graph.py
    uv run python scripts/run_graph.py "I get migraines twice a week"

The graph is STREAMED (see print_helpers.stream_graph): nodes emit progress events while they run
(planner done, each search, each lane...), one line is printed per finished node, and red flags appear
the moment they are recorded, instead of waiting several minutes for the final result.
"""

import json
import sys
import uuid
from pathlib import Path

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from ai_decision_arena.graph import build_graph
from print_helpers import ask_human_review, print_case, print_red_flags, print_report, stream_graph

question = " ".join(sys.argv[1:]) or "I have diabetes"

# The checkpointer saves state after every step; that's what makes pausing possible.
# InMemorySaver forgets everything when this script exits (PostgreSQL comes in Phase 7).
graph = build_graph(checkpointer=InMemorySaver())
print(graph.get_graph().draw_ascii())

# One thread_id = one session. Resuming needs the SAME thread_id.
thread_id = str(uuid.uuid4())
config = {
    "configurable": {"thread_id": thread_id},
    "run_name": "arena_graph",
    "metadata": {"thread_id": thread_id},   # LangSmith groups runs by thread_id
}
print(f"thread_id: {thread_id}\n")

shown_red_flags: set[str] = set()

result, payload = stream_graph(graph, {"question": question}, config, shown_red_flags)

# While the graph is paused, the stream ends with an "__interrupt__" update. Two kinds of pause:
# "red_flag" (a human must decide whether to go on) and "clarification" (questions to answer).
while payload is not None:
    snapshot = graph.get_state(config)
    print(f"\n⏸  Paused at node: {snapshot.next}  |  status: {snapshot.values.get('status')}")
    if payload.get("error") and payload.get("type") != "human_review":   # the review menu prints its own
        print(f"⚠️  {payload['error']}")

    if payload.get("type") == "human_review":
        reply = ask_human_review(payload)
        result, payload = stream_graph(graph, Command(resume=reply), config, shown_red_flags)
        continue

    if payload.get("type") == "red_flag":
        print("\n🚨 The warning above needs your decision. This tool gives information only, not medical care.")
        next_part = "the clarification questions" if payload["resume_to"] == "clarification" else "research and debate (~2-4 min)"
        answer = input(f"Type 'continue' to go on with {next_part} for later discussion with a doctor, "
                       f"or 'stop' to end now:\n> ").strip().lower()
        print()
        result, payload = stream_graph(graph, Command(resume={"action": answer}), config, shown_red_flags)
        continue

    print(f"\n🤔 Clarification round {payload['round']}. Press Enter to skip a question.\n")
    answers = {q: input(f"Q{i}: {q}\n> ") for i, q in enumerate(payload["questions"], start=1)}
    # We don't know yet whether clarification will ask again, so don't promise research.
    print("\n▶  Resuming. Checking your answers first; if no more questions are needed, research (~1 min) "
          "and debate (~2-3 min) follow. One line per finished node:\n")
    # Resume the SAME thread: the paused node continues, interrupt() returns this value.
    result, payload = stream_graph(graph, Command(resume={"answers": answers}), config, shown_red_flags)

print(f"\n✅ Finished with status: {result['status']}")
if result["status"] == "failed":
    err = result.get("error") or {}
    sys.exit(f"❌ {err.get('category', 'error')} in {err.get('node', '?')}: {err.get('message', '')}")
print_red_flags(result)
if result["status"] == "stopped_by_user":
    print("🛑 Stopped at your request before any research. Please seek medical care now; "
          "you can start a new session later.")
    print_case(result)
    sys.exit(0)
print_case(result)
print_report(result)

CACHE_DIR = Path(__file__).resolve().parent.parent / ".cache"
CACHE_DIR.mkdir(exist_ok=True)
(CACHE_DIR / "final_state.json").write_text(json.dumps(result, indent=2, default=str))
(CACHE_DIR / "final_report.json").write_text(json.dumps(result.get("final_report"), indent=2, default=str))
print(f"\n💾 Full state and report saved to {CACHE_DIR}/final_state.json and final_report.json "
      "(evidence, plans, criticisms and scores are all in there)")
