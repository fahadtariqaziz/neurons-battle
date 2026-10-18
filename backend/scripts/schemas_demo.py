"""Step 2.1 — see Pydantic validation in action. No API calls.

Run from the backend/ folder:
    uv run python scripts/schemas_demo.py
"""

import json

from pydantic import ValidationError

from ai_decision_arena.schemas import ClarificationResult, Evidence, Verdict


def show(title: str, fn) -> None:
    print(f"\n--- {title} ---")
    try:
        result = fn()
        print("✅ valid:", result)
    except ValidationError as exc:
        print(f"❌ rejected ({exc.error_count()} error(s)):")
        for err in exc.errors():
            print(f"   • {'.'.join(map(str, err['loc']))}: {err['msg']}")


# 1) A good evidence record
good = {
    "evidence_id": "ev_001",
    "source_title": "PostgreSQL Docs: Transactions",
    "source_url": "https://www.postgresql.org/docs/current/tutorial-transactions.html",
    "source_type": "official_documentation",
    "relevant_excerpt": "Transactions bundle multiple steps into a single, all-or-nothing operation.",
    "is_direct_quote": False,
    "claims_supported": ["PostgreSQL supports ACID transactions"],
    "relevance_score": 0.9,
}
show("Good evidence", lambda: Evidence.model_validate(good).evidence_id)

# 2) Bad evidence: wrong id format, invalid URL, unknown source type, score > 1
bad = good | {"evidence_id": "evidence-1", "source_url": "not a url",
              "source_type": "blog", "relevance_score": 1.7}
show("Bad evidence", lambda: Evidence.model_validate(bad))

# 3) Clarification: the exact field name `need_clarification` is required
show("Clarification OK", lambda: ClarificationResult(
    need_clarification=True, questions=["What is your expected workload?"], reason="Changes sizing."))
show("Clarification with wrong field name", lambda: ClarificationResult.model_validate(
    {"needs_clarification": True, "reason": "typo in field name"}))

# 4) Judge verdict: only the 4 allowed decisions
show("Verdict with unknown decision", lambda: Verdict(decision="pick_postgres", reason="I like it"))

# 5) How a model is stored in ArenaState: a plain JSON-friendly dict
print("\n--- Evidence as stored in state (model_dump) ---")
print(json.dumps(Evidence.model_validate(good).model_dump(mode="json"), indent=2))

# 6) This JSON schema is what Claude will see when it fills a model (structured output)
print("\n--- JSON schema Claude will receive for ClarificationResult ---")
print(json.dumps(ClarificationResult.model_json_schema(), indent=2))
