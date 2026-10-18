"""Step 4.1 — plan search queries with Claude, run them on Tavily, show the hits.

Run from the backend/ folder:
    uv run python scripts/run_research_plan.py

Uses a saved, already-clarified state (from a Step 3.3 run), so no questions are asked.
"""

from ai_decision_arena.research.planner import plan_queries
from ai_decision_arena.research.search import run_searches
from demo_data import CLARIFIED_STATE

print("🧠 Planning queries with Claude...\n")
plan = plan_queries(CLARIFIED_STATE)
print(f"Candidate options: {plan.candidate_options}\n")
for i, q in enumerate(plan.queries, 1):
    domains = f"  prefer={q.preferred_domains}" if q.preferred_domains else ""
    print(f"  Q{i} [{q.purpose:<20}] ({q.target_option}) {q.query}{domains}")

print("\n🔎 Searching with Tavily...\n")
hits, failures = run_searches(plan.queries)

for h in hits:
    print(f"  {h.tavily_score:.2f}  {h.source_type:<23} {h.title[:70]}")
    print(f"        {h.url}")
print(f"\n✅ {len(hits)} unique hits from {len(plan.queries)} queries")

if failures:
    print(f"⚠️  {len(failures)} failed queries (recorded as evidence gaps):")
    for f in failures:
        print(f"   - {f.query!r}: {f.error_type} (retryable={f.retryable})")
