"""Node 3 — Research: plan searches, run Tavily, turn results into structured Evidence.

Three lanes (research / doctor / patient) share one planner call, run their searches in
parallel, and each lane gets its own extractor call (also in parallel).

Writes (owner): research_queries, evidence, perspective_summaries, research_summary,
evidence_gaps, conflicting_claims, rejected_sources, status, current_node.

On a follow-up pass (Judge asked for more research or new clarification), only the open
questions are searched and new evidence is APPENDED; ids continue (ev_021, ...).
research_retry_count is incremented by the Judge node when it sends the graph back here,
not by this node (the first pass is not a retry).
"""

from ai_decision_arena.progress import report
from ai_decision_arena.research.extractor import extract_evidence
from ai_decision_arena.research.planner import plan_queries
from ai_decision_arena.research.search import run_searches
from ai_decision_arena.research.sources import normalize_url
from ai_decision_arena.schemas import PERSPECTIVES, PERSPECTIVE_LABELS, SearchHit
from ai_decision_arena.state import ArenaState


def _focus_for_follow_up(state: ArenaState) -> list[str] | None:
    """What a follow-up pass should look for: the Judge's open questions, plus any answers the
    user gave since (so research can re-check what changed). None on the first pass."""
    if not state.get("evidence"):
        return None
    verdict = state.get("verdict") or {}
    focus = list(verdict.get("required_evidence", []))
    if verdict.get("decision") == "request_clarification":
        # The clarification node may reword the Judge's questions, so don't match question text:
        # the planner already sees every answer in <clarification_answers>.
        focus.append("The user just answered the Judge's follow-up questions (see <clarification_answers>): "
                     "re-check what those answers change.")
    return focus or None


def research_node(state: ArenaState) -> dict:
    existing = list(state.get("evidence", []))
    focus = _focus_for_follow_up(state)

    # 1) Claude plans the queries for all three lanes.
    report("research", "planning searches for the 3 lanes" + (" (follow-up, focused on the Judge's open questions)" if focus else ""))
    plan = plan_queries(state, focus=focus)
    report("research", f"planned {len(plan.queries)} searches; running them in parallel")
    queries = [f"[{q.perspective}] {q.query}" for q in plan.queries]

    # 2) Tavily runs them in parallel. Skip URLs we already have evidence for.
    hits, failures = run_searches(plan.queries)
    known = {normalize_url(e["source_url"]) for e in existing}
    hits = [h for h in hits if normalize_url(h.url) not in known]
    report("research", f"{len(hits)} unique results" + (f", {len(failures)} search(es) failed" if failures else "") + "; extracting evidence per lane")
    by_lane: dict[str, list[SearchHit]] = {p: [h for h in hits if h.perspective == p] for p in PERSPECTIVES}

    gaps = [f"[{f.perspective}] Search failed for {f.query!r} ({f.error_type})" for f in failures]
    gaps += [f"[{p}] No search results for the {PERSPECTIVE_LABELS[p].split(' (')[0].lower()}"
             for p in PERSPECTIVES if not by_lane[p]]

    # 3) Claude extracts evidence per lane (skipped for empty lanes: never invent evidence).
    if hits:
        out = extract_evidence(state, by_lane, start_number=len(existing) + 1)
    else:
        out = {"evidence": [], "rejected": [], "conflicts": [], "gaps": [], "summaries": {}}
    gaps += out["gaps"]

    # Summaries: per lane (merged with earlier passes) and one combined text for printing.
    summaries = dict(state.get("perspective_summaries", {}))
    for p, text in out["summaries"].items():
        summaries[p] = f"{summaries[p]}\n\nFollow-up: {text}" if p in summaries else text
    combined = "\n\n".join(f"## {PERSPECTIVE_LABELS[p]}\n{summaries[p]}" for p in PERSPECTIVES if p in summaries)

    return {
        "research_queries": list(state.get("research_queries", [])) + queries,
        "evidence": existing + out["evidence"],
        "rejected_sources": list(state.get("rejected_sources", [])) + out["rejected"],
        "conflicting_claims": list(state.get("conflicting_claims", [])) + out["conflicts"],
        "evidence_gaps": gaps,     # replaced each pass: these are the CURRENT open gaps
        "perspective_summaries": summaries,
        "research_summary": combined or "No evidence was retrieved.",
        "status": "debating",
        "current_node": "research",
    }
