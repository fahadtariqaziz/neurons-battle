"""Query planning: Claude turns the clarified case into targeted searches for all three lanes."""

import json

from ai_decision_arena.config import get_settings
from ai_decision_arena.llm import call_structured
from ai_decision_arena.prompting import SAFETY_RULES, user_case_block
from ai_decision_arena.schemas import PERSPECTIVES, ResearchPlan, SearchQuery
from ai_decision_arena.state import ArenaState

SYSTEM_PROMPT = """You are the research planner of Health Decision Arena. Three lanes of web research run for the
user's condition, and every lane must answer the same questions: how people manage the condition day to day
(routine), what they eat (diet), which medications or treatments are used, how long until progress is seen,
and how common or rare the condition is.

Lanes:
- research: peer-reviewed studies, systematic reviews, meta-analyses (PubMed, Cochrane, journals).
- doctor: clinical guidelines and doctor-written references (WHO, CDC, NICE, NHS, Mayo Clinic, specialist societies).
- patient: real-world experiences and reviews from people living with the condition (Reddit, patient forums).

Rules:
- Return exactly {per_lane} queries per lane ({total} in total). Group them by lane, most important topic first.
- Each query combines the condition with ONE topic. Spread the topics so the lane covers routine, diet,
  medications, timeline and prevalence as far as the query budget allows (combine related topics in one query
  when needed, e.g. "diet and exercise").
- Exactly ONE query per lane must have topic overview_prevalence or progress_timeline and ask how common or
  rare the condition is and how long until improvement is typically seen (patient lane: "how long did it take
  to see improvement").
- Make queries specific to the user: type/stage, key medications, constraints (e.g. "vegetarian"),
  important symptoms. Patient-lane queries should sound like how people talk ("what worked", "experience").
- Queries are short keyword searches, not sentences. No years unless recency matters.
- preferred_domains: only condition-specific official organisations you are sure about
  (e.g. diabetes.org for diabetes); empty list otherwise. General medical sites are added automatically.
- If <focus> is non-empty this is a FOLLOW-UP search: target ONLY those open questions, still one lane per
  query, and still cover all three lanes.
""" + SAFETY_RULES

LANE_ORDER = {p: i for i, p in enumerate(PERSPECTIVES)}


def plan_queries(state: ArenaState, focus: list[str] | None = None) -> ResearchPlan:
    settings = get_settings()
    per_lane = settings.queries_per_perspective
    user_content = f"""{user_case_block(state)}
<focus>{json.dumps(focus or [], indent=2)}</focus>"""

    plan = call_structured(
        ResearchPlan,
        SYSTEM_PROMPT.replace("{per_lane}", str(per_lane)).replace("{total}", str(per_lane * len(PERSPECTIVES))),
        user_content,
        max_tokens=2500,
        run_name="research_planner_llm",
    )
    # Python enforces the budget per lane even if Claude returns more, and fixes the lane order.
    kept: list[SearchQuery] = []
    count = {p: 0 for p in PERSPECTIVES}
    for q in plan.queries:
        if count[q.perspective] < per_lane:
            count[q.perspective] += 1
            kept.append(q)
    if focus is None:
        kept = _ensure_outlook_query(kept, plan.search_term, per_lane)
    plan.queries = sorted(kept, key=lambda q: LANE_ORDER[q.perspective])
    return plan


OUTLOOK_TOPICS = ("overview_prevalence", "progress_timeline")
OUTLOOK_QUERY = {
    "research": "{term} prevalence epidemiology and time to improvement with treatment",
    "doctor": "{term} how common is it typical course how long until symptoms improve",
    "patient": "{term} how long did it take to see improvement experience",
}


def _ensure_outlook_query(queries: list[SearchQuery], term: str, per_lane: int) -> list[SearchQuery]:
    """The user always gets 'how common is it' and 'how long until progress'. If Claude spent a lane's
    whole budget elsewhere, the lane's last query is replaced by a fixed prevalence/timeline query.
    (Only on the first pass: follow-up searches are focused on the Judge's open questions.)"""
    result = list(queries)
    for perspective in PERSPECTIVES:
        lane = [q for q in result if q.perspective == perspective]
        if any(q.topic in OUTLOOK_TOPICS for q in lane):
            continue
        fallback = SearchQuery(
            query=OUTLOOK_QUERY[perspective].format(term=term), perspective=perspective,
            topic="overview_prevalence", preferred_domains=[],
        )
        if len(lane) >= per_lane:
            result.remove(lane[-1])      # lowest-priority query of the lane makes room
        result.append(fallback)
    return result
