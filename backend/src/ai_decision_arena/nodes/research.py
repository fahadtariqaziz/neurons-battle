"""Node 3 — Research: plan searches, run Tavily, turn results into structured Evidence.

Writes (owner): research_queries, evidence, research_summary, evidence_gaps,
conflicting_claims, rejected_sources, status, current_node.

On a follow-up pass (later: Judge/Checker asks for more research), only the open questions
are searched and new evidence is APPENDED; ids continue (ev_021, ...).
research_retry_count is incremented by the routing step that sends the graph back here,
not by this node (the first pass is not a retry).
"""

from ai_decision_arena.research.extractor import extract_evidence
from ai_decision_arena.research.planner import plan_queries
from ai_decision_arena.research.search import run_searches
from ai_decision_arena.research.sources import normalize_url
from ai_decision_arena.state import ArenaState


def research_node(state: ArenaState) -> dict:
    existing = list(state.get("evidence", []))
    # Follow-up pass: search only what the Judge said is missing. First pass: no focus.
    focus = None
    if existing:
        focus = (state.get("verdict") or {}).get("required_evidence") or None

    # 1) Claude plans the queries.
    plan = plan_queries(state, focus=focus)
    queries = [q.query for q in plan.queries]

    # 2) Tavily runs them. Skip URLs we already have evidence for.
    hits, failures = run_searches(plan.queries)
    known = {normalize_url(e["source_url"]) for e in existing}
    hits = [h for h in hits if normalize_url(h.url) not in known]

    gaps = [f"Search failed for {f.query!r} ({f.error_type})" for f in failures]

    # 3) Claude extracts evidence (skipped if nothing came back: never invent evidence).
    if hits:
        evidence, rejected, conflicts, extra_gaps, summary = extract_evidence(
            state, hits, start_number=len(existing) + 1
        )
        gaps += extra_gaps
    else:
        evidence, rejected, conflicts, summary = [], [], [], "No new search results were retrieved."
        gaps.append("No search results available for this research pass.")

    previous_summary = state.get("research_summary", "")
    return {
        "research_queries": list(state.get("research_queries", [])) + queries,
        "evidence": existing + evidence,
        "rejected_sources": list(state.get("rejected_sources", [])) + rejected,
        "conflicting_claims": list(state.get("conflicting_claims", [])) + conflicts,
        "evidence_gaps": gaps,     # replaced each pass: these are the CURRENT open gaps
        "research_summary": f"{previous_summary}\n\n{summary}".strip() if existing else summary,
        "status": "debating",
        "current_node": "research",
    }
