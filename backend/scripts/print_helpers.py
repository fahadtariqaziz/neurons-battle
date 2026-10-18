"""Shared terminal printing for the demo scripts."""


def print_research(state: dict) -> None:
    evidence = state.get("evidence", [])
    print(f"\n🔎 Queries ({len(state.get('research_queries', []))}):")
    for q in state.get("research_queries", []):
        print(f"   - {q}")

    print(f"\n📚 Evidence kept: {len(evidence)}")
    for e in evidence:
        quote = "quote" if e["is_direct_quote"] else "paraphrase"
        print(f"\n  {e['evidence_id']}  [{e['source_type']}]  relevance={e['relevance_score']:.2f}  ({quote})")
        print(f"     {e['source_title'][:90]}")
        print(f"     {e['source_url']}")
        print(f"     \"{e['relevant_excerpt'][:200]}\"")
        if e.get("claims_supported"):
            print(f"     claims: {e['claims_supported'][:2]}")
        if e.get("community"):
            c = e["community"]
            print(f"     community: recurring={c['is_recurring']} | {c['issue_discussed'][:100]}")
        print(f"     notes: {e['reliability_notes'][:160]}")

    rejected = state.get("rejected_sources", [])
    print(f"\n🗑  Rejected sources: {len(rejected)}")
    for r in rejected:
        print(f"   - {r['title'][:60]:<60}  → {r['reason'][:80]}")

    print("\n🕳  Evidence gaps:")
    for g in state.get("evidence_gaps", []) or ["(none)"]:
        print(f"   - {g}")

    print("\n⚔️  Conflicting claims:")
    for c in state.get("conflicting_claims", []) or [{"topic": "(none)", "evidence_ids": [], "description": ""}]:
        print(f"   - {c['topic']} {c['evidence_ids']} {c['description'][:120]}")

    print(f"\n📝 Summary:\n{state.get('research_summary', '')}")
