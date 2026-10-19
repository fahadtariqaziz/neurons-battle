"""Node 2 — Clarification: decide if we must ask the user something, then pause to ask.

Split into TWO graph nodes on purpose:
- clarification_node        (LLM)   decides: ask or not? Never pauses.
- await_clarification_node  (human) calls interrupt() and stores the answers.

Why split? On resume, LangGraph re-runs the paused node FROM ITS FIRST LINE.
If the Claude call lived in the same node as interrupt(), it would run again on resume:
extra cost, and possibly DIFFERENT questions than the ones the user just answered.

Loop: clarification → await_clarification → clarification → ... → research
The Judge can also send the graph back here with its own questions (verdict.clarification_questions).

Writes (owner): need_clarification, clarification_questions, clarification_answers,
assumptions, clarification_round_count; also merges new profile facts / symptoms / constraints / red flags.
"""

import json

from langgraph.types import interrupt
from pydantic import ValidationError

from ai_decision_arena.config import get_settings
from ai_decision_arena.llm import call_structured
from ai_decision_arena.nodes.red_flag_ack import pending_red_flags
from ai_decision_arena.progress import report
from ai_decision_arena.prompting import SAFETY_RULES, user_case_block
from ai_decision_arena.schemas import ClarificationAnswers, ClarificationResult
from ai_decision_arena.state import ArenaState

MAX_QUESTIONS_PER_ROUND = 6
MAX_ANSWER_CHARS = 2000

SYSTEM_PROMPT = """You are the Clarification agent of Health Decision Arena, a system that explains how a health
condition is managed from three perspectives: published research, doctors, and other patients.

Decide whether the user must answer questions BEFORE research starts, and write those questions.

FIRST ROUND (no previous answers yet): ask 5-6 short questions so the research fits this person. Cover,
unless already stated: (1) exact type/stage and whether a doctor confirmed it, (2) how long they have had it,
(3) current symptoms and when they occur, (4) current medications or treatments tried, (5) other conditions,
allergies or pregnancy, (6) daily routine, diet and what they want to achieve. Skip anything already answered.

LATER ROUNDS: ask again ONLY if an answer revealed something that materially changes the research
(e.g. "type 1" instead of "type 2", pregnancy, a new red-flag symptom). Otherwise set need_clarification to false.

If <judge_questions> is non-empty, the Judge needs those answers to rank the plans: ask them (reworded if
helpful) plus anything else essential, within the limit.

Rules:
- At most {max_questions} questions per round, in plain language. ONE question = ONE answer: never pack several
  sub-questions into one (not "does it come and go, did it start suddenly, one eye or both?"). If a topic has
  several sub-questions, ask only the single most useful one, with example answers in brackets.
- Never ask about something the user already stated or already answered.
- Put new facts from the user's answers into new_profile_facts / new_symptoms / new_constraints.
  Extract only what the user actually said. An answer of "(skipped by user)" means unknown.
- Put emergency warning signs the answers reveal into new_red_flags (e.g. a type 1 patient on tablets only
  who reports vomiting or fast breathing). Red flags must be shown to the user, so never leave them only in
  assumptions. Only GENUINELY NEW signs: never repeat or reword a flag already listed in <red_flags>.
- When screening for warning signs, ask "Which of these do you have right now: ...?" instead of a yes/no list,
  so a one-word answer cannot be ambiguous.
- If can_ask_more is false, you MUST set need_clarification to false.
- Whenever need_clarification is false, list explicit assumptions for important info that is still missing.
""" + SAFETY_RULES


def _build_user_content(state: ArenaState, can_ask_more: bool) -> str:
    judge_questions = (state.get("verdict") or {}).get("clarification_questions", [])
    return f"""{user_case_block(state)}
<missing_information>{json.dumps(state.get("missing_information", []), indent=2)}</missing_information>
<judge_questions>{json.dumps(judge_questions, indent=2)}</judge_questions>
<rounds_used>{state.get("clarification_round_count", 0)}</rounds_used>
<can_ask_more>{str(can_ask_more).lower()}</can_ask_more>"""


def clarification_node(state: ArenaState) -> dict:
    """LLM decision: do we need more input? (No interrupt here.)"""
    settings = get_settings()
    rounds_used = state.get("clarification_round_count", 0)
    can_ask_more = rounds_used < settings.max_clarification_rounds

    report("clarification", "deciding whether questions are needed" if rounds_used == 0 else "reading your answers and deciding whether to ask more")
    result = call_structured(
        ClarificationResult,
        SYSTEM_PROMPT.replace("{max_questions}", str(MAX_QUESTIONS_PER_ROUND)),
        _build_user_content(state, can_ask_more),
        max_tokens=2000,
        run_name="clarification_llm",
    )

    # Merge facts learned from the user's answers.
    profile = dict(state.get("health_profile", {}))
    profile.update({item.name: item.value for item in result.new_profile_facts})
    symptoms = dict(state.get("symptoms", {}))
    symptoms.update({item.name: item.value for item in result.new_symptoms})
    constraints = dict(state.get("constraints", {}))
    constraints.update({item.name: item.value for item in result.new_constraints})
    red_flags = list(state.get("red_flags", []))
    red_flags += [flag for flag in result.new_red_flags if flag not in red_flags]

    # Python has the final say on routing, not the LLM:
    # no asking past the round limit, no repeated questions, no empty question lists.
    already_asked = set(state.get("clarification_answers", {}))
    questions = [q for q in result.questions if q not in already_asked][:MAX_QUESTIONS_PER_ROUND]
    need = result.need_clarification and can_ask_more and bool(questions)

    update = {
        "health_profile": profile,
        "symptoms": symptoms,
        "constraints": constraints,
        "red_flags": red_flags,
        "need_clarification": need,
        "clarification_questions": questions if need else [],
        "clarification_reason": result.reason,
        "current_node": "clarification",
    }
    if need:
        update["status"] = "awaiting_clarification"
    else:
        assumptions = result.assumptions
        if not assumptions and not state.get("assumptions"):
            # Never continue silently: record what is still unknown, without guessing values.
            assumptions = [f"Not specified by user: {item}" for item in state.get("missing_information", [])]
        update["assumptions"] = list(state.get("assumptions", [])) + [a for a in assumptions if a not in state.get("assumptions", [])]
        # New emergency signs in the answers → the graph pauses for a human decision before research.
        update["status"] = "awaiting_red_flag_ack" if pending_red_flags(state | {"red_flags": red_flags}) else "researching"
    return update


def await_clarification_node(state: ArenaState) -> dict:
    """Human input: pause the graph until the user answers. (No LLM here.)"""
    questions = state.get("clarification_questions", [])
    payload = {
        "type": "clarification",
        "questions": questions,
        "round": state.get("clarification_round_count", 0) + 1,
    }

    # Keep asking until the answer is valid. Each interrupt() is a separate pause.
    error = None
    while True:
        raw = interrupt((payload | {"error": error}) if error else payload)
        try:
            answers = ClarificationAnswers.model_validate(raw).answers
        except ValidationError as exc:
            error = f"Invalid answer format: {exc.errors()[0]['msg']}"
            continue
        unknown = set(answers) - set(questions)
        if unknown:
            error = f"Answers given for questions that were not asked: {sorted(unknown)}"
            continue
        break

    # Store every asked question; unanswered ones are recorded as skipped.
    cleaned = {
        q: (answers.get(q) or "").strip()[:MAX_ANSWER_CHARS] or "(skipped by user)"
        for q in questions
    }
    return {
        "clarification_answers": {**state.get("clarification_answers", {}), **cleaned},
        "clarification_round_count": state.get("clarification_round_count", 0) + 1,
        "clarification_questions": [],
        "current_node": "await_clarification",
    }
