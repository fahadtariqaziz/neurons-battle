# Health Decision Arena — Handoff

> **Read this first in every new session.** It records the plan, how we work, what's done, and what's next.

## How we work (agreed workflow)
- We build in **small steps**. One step finishes → we check it → we move on.
- Each step is tagged **[YOU]** (user does it, sends a screenshot) or **[CLAUDE]** (Claude implements it).
- Before each [CLAUDE] step, Claude explains briefly: **what** it will build, **why**, **how**, and **prerequisites** to understand it.
- Claude asks questions when something is unclear instead of guessing.
- After each step, update the **Progress Log** and **Next Step** sections below.
- Goal is **learning** as well as a working app — prefer simple, readable code first, then add features.
- **Git:** Claude never commits/pushes. After each step Claude gives a commit name; the user tests, commits and pushes (repo: github.com/fahadtariqaziz/neurons-battle).
- **Testing:** No automated test suite — the user tests manually by running things. Claude gives exact commands to run + what output to expect, and the user shares script output + LangSmith traces.

## Project summary
A user describes a health condition ("I have diabetes"). Instead of one LLM answer, agents
clarify the user's situation (5–6 questions) → research the web from **three perspectives**
(research papers · doctors/clinical guidance · patients' real-world experiences) → propose 2–3 care
plans per perspective → critique → judge/score → verify evidence → let the human review → write a
final report with **one best plan per perspective**. Every plan covers: daily routine, diet,
medications/treatments as reported, expected time to progress, and whether the condition is common or rare.

The system gives **health information to discuss with a clinician** — it never diagnoses, prescribes,
invents doses or advises stopping medication, and it flags red-flag symptoms.

History: the project started (2026-10-18) as a *technical* decision arena. On **2026-10-20** it pivoted to
health conditions. Original brief: `docs/requirements.md` (architecture + engineering rules still apply).
What changed and the concept mapping: `docs/pivot-medical.md`.

## Tech stack (fixed)
| Area | Choice |
|---|---|
| Orchestration | LangGraph (StateGraph, conditional edges, `interrupt()`) |
| LLM | Anthropic Claude **only** (via `langchain-anthropic`) |
| Web research | Tavily |
| Tracing | LangSmith (project: `ai-decision-arena`) |
| Backend | Python 3.13 + FastAPI + Pydantic, managed with `uv` |
| Persistence | PostgreSQL 16 (local, Homebrew) + LangGraph Postgres checkpointer + SQLAlchemy/Alembic |
| Frontend | Next.js + TypeScript + Tailwind CSS |

Local machine (checked 2026-10-18): Python 3.13.12, uv installed, Node 22.22.1, PostgreSQL 16 (Homebrew).
Python package is still named `ai_decision_arena` (see Open questions).

## Graph design (11 logical nodes)
```
START → intake ──(red flags in first message)──► await_red_flag_ack (interrupt: continue / stop) ─┐
          │ no                                              stop → END (stopped_by_user)       │ continue
          ▼◄───────────────────────────────────────────────────────────────────────────────────┘
      clarification ──(need_clarification? interrupt & loop, max 2 rounds)──┐
          │ no                                                              │
          ├──(new red flags)──► await_red_flag_ack (continue → research / stop → END)
          ▼                                                                 │
                  research  (3 lanes: research / doctor / patient; parallel)            │
                      ▼                                                                 │
                  proposer → critic → judge ──(request_clarification)──► clarification ─┘
                      ▲                 │
                      └─(request_more_research, focused)
                                        │ proceed / insufficient_evidence
                                        ▼
                               evidence_checker ──(material gap, retries left)──► research
                                        ▼
                                 human_review (interrupt) ──(revise / more research / new round, bounded)
                                        │ approve
                                        ▼
                                  final_report → completion → END

Any node failure → error_recovery → (retry same node | completion with status=failed)
```
Loop limits: debate rounds ≤ 2, research retries ≤ 2 (first pass isn't a retry), clarification rounds ≤ 2.
Because every judge-triggered loop starts a new debate round, with the defaults the judge can loop at most
once (debate cap binds first). Raise `MAX_DEBATE_ROUNDS` to allow more.

Per-perspective design: Research tags every evidence item with a `perspective`. Proposer / Critic / Judge
each run **three parallel LLM calls (one per lane)**. Plan ids are `research_a`, `doctor_b`, `patient_c`…
The Judge's `verdict.winning_plan_ids` holds one winner per lane.

## Implementation plan (small steps)

### Phase 0 — Setup ✅
- [x] 0.1–0.4 Keys, uv project, `.env`, `scripts/check_env.py` (Claude/Tavily/LangSmith ping).

### Phase 1 — LangGraph basics (learning) ✅
- [x] 1.1–1.3 `hello_graph.py`, `claude_graph.py`, first LangSmith trace.

### Phase 2 — Real state & schemas ✅ (re-done for health on 2026-10-20)
- [x] 2.1 `schemas.py` (Perspective, ConditionCategory, Evidence w/ perspective + strength, CarePlan, PlanScore, Verdict, FinalReport…), `state.py`, `scripts/schemas_demo.py`.
- [x] 2.2 `config.py`: health rubric (fit_to_user .30, safety .25, evidence_quality .20, practicality .15, completeness .10), per-lane research limits. Demo: `scripts/config_demo.py`.

### Phase 3 — Intake + Clarification ✅ (re-done for health)
- [x] 3.1 `nodes/intake.py`: condition name/category, health_profile, symptoms, constraints, missing info, red flags. `scripts/run_intake.py`.
- [x] 3.2 `nodes/clarification.py`: first round asks 5–6 questions; later rounds only if material; accepts Judge questions. `prompting.py` shared blocks + safety rules.
- [x] 3.3 [YOU] Run CLI, answer questions, screenshot trace. *(re-verify after pivot in 5.4)*

### Phase 4 — Research ✅ (re-done for 3 lanes)
- [x] 4.1 `research/planner.py` (3 queries per lane), `research/search.py` (lane domain steering: research/doctor "prefer" medical domains; patient "restrict" to forums + advanced depth), `research/sources.py` (medical classifier). Demo: `scripts/run_research_plan.py`.
- [x] 4.2 `research/extractor.py` (one call per lane, in parallel; ids assigned after all lanes) + `nodes/research.py`. Scripts: `run_research.py` (saves `.cache/research_state.json`), `run_graph.py`, `demo_data.py`, `print_helpers.py`.

### Phase 5 — Debate ✅ built 2026-10-20 (awaiting user test + commit)
- [x] 5.1 `nodes/proposer.py`: 3 parallel calls → 2–3 `CarePlan`s per lane from that lane's evidence only; Python assigns ids, drops unknown evidence ids (visible as a gap), clears old criticisms/scores, `debate_round += 1`.
- [x] 5.2 `nodes/critic.py`: 3 parallel calls; each lane's plans vs ALL evidence; exactly one `Criticism` per plan (Python fills missing ones); evidence ids validated.
- [x] 5.3 `nodes/judge.py`: 3 parallel calls → `PerspectiveJudgement` (criterion scores + sufficiency + required evidence + questions). Python: weighted totals, winner per lane, routing within limits, `research_retry_count += 1` when looping. `graph.py`: research → proposer → critic → judge → (research | clarification | END).
- [x] 5.4 [YOU] Ran `run_intake.py`, `run_research.py`, `run_debate.py`, `run_graph.py` (type 1 scenario) + LangSmith traces → verified 2026-10-20. Commit pending.
- [x] 5.6 [CLAUDE] Red-flag pause: `await_red_flag_ack` interrupt node (continue / stop) after intake or clarification whenever unacknowledged red flags exist. User decision 2026-10-20: "humans remain in control of high-risk decisions".
- [x] 5.5 [CLAUDE] Live progress events (`progress.report`) in every node + `print_helpers.stream_graph` used by all run scripts. Built 2026-10-20 after the user asked for an "agents at work" view; same events will feed the frontend activity view (Phase 8/9).

### Phase 6 — Verification & finishing nodes
- [ ] 6.1 [CLAUDE] Evidence Checker: verify the claims of the 3 winning plans (+ runners-up) against stored evidence; statuses; route back to research if a material gap and retries remain.
- [ ] 6.2 [CLAUDE] Human Review node (interrupt; validated `HumanReviewInput`: approve / reject / request_debate_round / request_more_research / modify_profile / add_context / select_plan).
- [ ] 6.3 [CLAUDE] Final Report (3 `PerspectiveResult`s, agreements/differences, uncertainties, disclaimer) + Completion nodes.
- [ ] 6.4 [CLAUDE] Error Recovery node + retries/backoff + per-session time budget.
- [ ] 6.5 [YOU] Full CLI run end-to-end, screenshot LangSmith trace.

### Phase 7 — PostgreSQL
- [ ] 7.1 [YOU] Start Postgres, create database `ai_decision_arena`.
- [ ] 7.2 [CLAUDE] Swap InMemorySaver → PostgresSaver; test resume after restart.
- [ ] 7.3 [CLAUDE] SQLAlchemy models + Alembic migrations (sessions, evidence, reports, feedback).

### Phase 8 — FastAPI backend
- [ ] 8.1 [CLAUDE] Endpoints: create / status / resume / report / evidence / feedback, background execution + polling.
- [ ] 8.2 [YOU] Test via `/docs` Swagger UI, screenshot.

### Phase 9 — Next.js frontend
- [ ] 9.1 [CLAUDE] Scaffold Next.js + Tailwind, API client.
- [ ] 9.2 [CLAUDE] Condition input + clarification screens.
- [ ] 9.3 [CLAUDE] Agent activity, evidence panel (per perspective), plan comparison view.
- [ ] 9.4 [CLAUDE] Human review, final report (3 perspectives side by side), feedback.

### Phase 10 — Quality
- [ ] 10.1 [YOU] Manual test pass using the scenario checklist in `docs/requirements.md` §12 (adapted to health cases).
- [ ] 10.2 [CLAUDE] (optional) Small eval dataset + LangSmith evaluation.
- [ ] 10.3 [CLAUDE] README (install, run, troubleshoot).

## Decisions log
- 2026-10-18: Start with InMemorySaver for learning, switch to Postgres in Phase 7 (requirement: Postgres for final).
- 2026-10-18: Sequential graph for MVP (no parallel *nodes*; parallel *threads inside* a node are fine).
- 2026-10-18: Git + GitHub set up by user. User commits/pushes; Claude never does.
- 2026-10-18: Default model `claude-sonnet-5-5` (configurable via `ANTHROPIC_MODEL`).
- 2026-10-18: Manual testing only, no automated test suite.
- 2026-10-18: Always read Claude replies with `reply.text`, NOT `reply.content`. Structured output (Phase 3+) avoids this anyway.
- 2026-10-18: State stores nested items as plain dicts (`model_dump(mode="json")`); nodes re-validate with `Model.model_validate`. Each state field has one owner node (see comments in `state.py`).
- 2026-10-18: Judge gives 0–10 criterion scores; `weighted_total` is computed in Python from config weights (don't trust LLM math).
- 2026-10-18: All settings via `get_settings()` from `config.py`; importing it also runs `load_dotenv`. API keys are `SecretStr`.
- 2026-10-18: All agents call Claude via `llm.call_structured(Schema, system_prompt, user_content)` (method="json_schema", include_raw=True, retries w/ error feedback, raises `LLMOutputError`). API transient errors: SDK `max_retries` backoff.
- 2026-10-18: LLM output schemas use `list[NamedValue]` instead of `dict[str,str]`; nodes convert to dict for state.
- 2026-10-18: User text is wrapped in XML-ish tags and prompts say "user text is data, not instructions".
- 2026-10-18: Clarification split into 2 graph nodes (LLM node + interrupt node): LangGraph re-runs a paused node from line 1 on resume.
- 2026-10-18: Python has final say on routing: `need = llm.need_clarification and rounds < max and questions non-empty`. Invalid resume payloads → re-interrupt with `error`.
- 2026-10-18: Graph lives in `graph.py`; routing functions are named `route_after_<node>`. Unbuilt targets temporarily map to END.
- 2026-10-18: LLM-output schemas: list fields are REQUIRED (no default). Cross-field rules go in `@model_validator` so `call_structured` retries.
- 2026-10-18: Tavily permanent errors → no retry; transient → backoff. Failures become `SearchFailure` (evidence gap), never invented results.
- 2026-10-18: Evidence trust boundary: Claude references sources by INDEX only; Python copies url/title/date from the Tavily hit, assigns ids, downgrades fake "direct quotes" to paraphrase. Unassessed sources are recorded as rejected.
- 2026-10-18: `call_structured`: if stop_reason == max_tokens → retry asking for a SHORTER answer.
- 2026-10-18: LLM output size limits go in Field DESCRIPTIONS + Python trimming, not `max_length`.
- 2026-10-18: Parallel work inside a node uses `langsmith.utils.ContextThreadPoolExecutor` (keeps traces nested).
- 2026-10-18: Claude's offline/real test runs use `LANGSMITH_TRACING=false` so they don't clutter the user's LangSmith project.
- 2026-10-18: Backend uses uv "src layout": code in `backend/src/ai_decision_arena/`; `.env` lives in `backend/`.
- **2026-10-20: PIVOT to health conditions.** Same 11 nodes, new purpose. Mapping in `docs/pivot-medical.md`. Package/LangSmith names unchanged to avoid churn.
- 2026-10-20: Three perspectives are first-class: `Perspective = research | doctor | patient`, carried on `SearchQuery → SearchHit → Evidence → CarePlan`. Research, Proposer, Critic, Judge run 3 parallel lane calls each (keeps each LLM output small, no max_tokens truncation; wall time ≈ one call).
- 2026-10-20: Lane domain lists are Python-owned (`research/sources.py`): research/doctor use Tavily `prefer` (planner may add ≤3 condition-specific domains), patient uses `restrict` + `search_depth=advanced` (basic gave too-short forum snippets). Classifier checks patient paths (`/comments/`, `/r/`, `/reviews`) before host hints.
- 2026-10-20: Extractor runs per lane; evidence ids are assigned in Python AFTER all lanes return (research → doctor → patient), so ids are unique and continue across passes. Extractor may re-label a hit's perspective (a forum thread found by a clinical query becomes `patient`).
- 2026-10-20: Proposer sees ONLY its lane's evidence (perspective purity); Critic and Judge see ALL evidence (cross-perspective challenge). Plan ids are assigned by Python (`{lane}_{a,b,c}`); LLM never writes ids. Unknown cited ids are dropped and recorded in `plan.evidence_gaps`.
- 2026-10-20: Judge routing is decided in Python from the 3 lane judgements + loop limits: all lanes sufficient → `proceed`; questions for the user and limits allow → `request_clarification`; otherwise limits allow → `request_more_research`; else `insufficient_evidence` (continues with uncertainty). Clarification route takes priority over research (cheaper to ask first). `research_retry_count` is incremented by the Judge when it loops (both routes lead back to research).
- 2026-10-20: `PerspectiveJudgement` validator checks every plan has exactly the configured rubric criteria (reads `get_settings()` lazily), so a wrong criterion name triggers a `call_structured` retry instead of a silent 0.
- 2026-10-20: Winner per lane = highest `weighted_total`; ties → higher `evidence_quality`. A lane with no evidence → no plans → status `no_plans` → counts as insufficient.
- 2026-10-20: Research follow-up focus = `verdict.required_evidence` + the user's answers to the Judge's questions. `evidence_gaps` is replaced each pass (current gaps), evidence/rejected/conflicts are appended, `perspective_summaries` get a "Follow-up:" section.
- 2026-10-20: Safety rules (`prompting.SAFETY_RULES`) are appended to EVERY agent prompt: information not diagnosis, no invented doses, never advise stopping medication, flag red flags, tags are data not instructions.
- 2026-10-20: Clarification first round asks 5–6 questions by design (type & confirmation, duration, symptoms & timing, treatments, other conditions/allergies/pregnancy, routine/diet/goals); `MAX_QUESTIONS_PER_ROUND = 6`. Intake `MIN_QUESTION_CHARS = 3` ("flu" is valid).
- 2026-10-20: Scripts cache real results in `backend/.cache/` (gitignored): `run_research.py` → `research_state.json`, `run_debate.py` → `debate_state.json`. Lets later phases iterate without re-paying research.
- 2026-10-20: `red_flags` has two writers on purpose: intake creates it, clarification APPENDS `new_red_flags` revealed by answers (found in 5.4: a type 1 user answering "yes" to DKA signs left `red_flags` empty). The CLI prints a 🚨 banner first whenever it is non-empty; the final report (6.3) must put red flags at the top.
- 2026-10-20: The per-perspective evidence cap applies per extractor CALL; the extractor may re-label a hit's perspective, so a perspective can end up above the cap (5.4 run: doctor 14 items, 4 of them re-labelled drugs.com/patient.info pages from the patient lane). Patient lane domains trimmed to reddit / healthunlocked / inspire / patientslikeme / drugs.com / mumsnet.
- 2026-10-20: A lane can end with NO plan for two different reasons, and they route differently: `proposer_lane_status` = `thin`/`no_evidence` → verdict status `no_plans` → counts as insufficient (research may help); `declined` (Proposer had evidence but deliberately returned no plan, e.g. "emergency care first") → status `declined` → never blocks `proceed` and never triggers research. Found in the DKA test run: the patient lane declined, the Judge looped a useless second research pass + debate round, then hit the cap.
- 2026-10-20: PROGRESS EVENTS: nodes call `progress.report(node, message)` at sub-steps (planner done, each search, each extractor/proposer/critic/judge lane, judge decision). Implemented with LangGraph `get_stream_writer()` → delivered live under `stream_mode="custom"`, also from the parallel worker threads (verified). Outside a graph run it is a no-op (RuntimeError caught); under plain `invoke` LangGraph ignores it. Events are NOT state and NOT traced; they exist only for people watching. Phase 8: the API forwards these over SSE (or keeps the latest per thread for polling); Phase 9: the activity view renders them.
- 2026-10-20: All run scripts go through `print_helpers.stream_graph(graph, input, config)` which streams `["custom", "updates", "values"]`: `·` lines for progress, `✔` per finished node, red flags immediately, and returns the last `values` chunk as the final state (works without a checkpointer too).
- 2026-10-20 (superseded by the above): `run_graph.py` STREAMS the graph (`stream_mode="updates"`): one line per finished node, red flags printed the moment intake/clarification record them, interrupts arrive as an `__interrupt__` chunk, final state read from `graph.get_state(config).values`. Pattern to reuse in the FastAPI layer (Phase 8) for live progress.
- 2026-10-20: Design choice (open for user): when red flags are present the graph still researches and debates (plans lead with emergency guidance). Alternative: pause after clarification and ask whether to continue. See Open questions.
- 2026-10-20: EMERGENCY RULE in the Proposer: when `red_flags` is non-empty each lane returns exactly ONE "Emergency first: ..." plan (urgent care now, then that lens's after-assessment guidance) instead of declining, so the user still gets three perspectives. Found in the secondary-diabetes run: doctor lane built an emergency plan while research and patient lanes declined → only one perspective. Declining remains for lanes with no usable evidence. The Critic is told an emergency-first single plan is correct and to check its urgency is unconditional.
- 2026-10-20: RED-FLAG PAUSE (user decision: option 1, human in control). `nodes/red_flag_ack.py`: `pending_red_flags(state)` = red_flags minus `red_flags_acknowledged`. Two entry points: `route_after_intake` (emergency sign in the first message → pause BEFORE the questions) and `route_after_clarification` (answers revealed one → pause before research). Payload `{type: "red_flag", red_flags, resume_to, options}`; reply `{"action": "continue"|"stop"}` validated by `RedFlagResponse`, invalid → re-interrupt with `error`. `continue` → resumes at `red_flag_resume_to` and records the flags shown at that moment; `stop` → END with status `stopped_by_user`, nothing researched. The decision is made ONCE per session (`pending_red_flags` is empty once `red_flag_action == "continue"`): later flags are shown in the banner immediately but never pause again. First version re-paused for "new" flags; the user's test showed two prompts within a minute, partly because the LLM reworded already-acknowledged flags (text matching is not semantic). Clarification prompt now says: only genuinely new signs, never reword existing ones. Statuses added: `awaiting_red_flag_ack`, `stopped_by_user`. No LLM in the pause node.
- 2026-10-20: After "continue" the emergency rules still apply (one emergency-first plan per lane, no Judge loops): consent to continue is not consent to wait twice as long.
- 2026-10-20: EMERGENCY = NO LOOPS in the Judge: when `red_flags` is non-empty, `can_loop` is False, so an insufficient lane yields `insufficient_evidence` (continue with uncertainty) instead of a research retry or clarification detour. Found in the "unsure type + deep breathing" run: a second research pass + debate added 2.3 min after the user had already been told to seek urgent care. The Judge prompt also says to judge emergency-first plans on their urgent-care guidance; thin after-assessment evidence lowers evidence_quality rather than sufficiency.
- 2026-10-20: Observed real timings (progress lines): research 45–53 s (planner 5 s, 9 searches 4 s, extractors 35 s), proposer 13–28 s, critic 25–67 s (slowest node; one lane with 3 plans and 14 points took 43 s), judge 11–21 s. Speed-up candidates if needed later: cap critic points at 4 per plan, shorter evidence excerpts for the critic, Haiku for the extractor.
- 2026-10-20: Clarification rule "ONE question = ONE answer" (no sub-question packs): a 4-part blurred-vision question got the answer "yes". Second occurrence of compound questions; if it recurs, enforce in Python (reject questions containing more than one "?" or " or " chains) rather than in the prompt.
- 2026-10-20: Improvement idea (not done): follow-up research re-searches ALL three lanes; a lane-targeted follow-up (only lanes named in `required_evidence`) would save ~40 s and tokens per loop. Needs the `ResearchPlan` all-lanes validator relaxed for follow-ups.
- 2026-10-20: Known limitation: `evidence_strength` and `prevalence` come from snippets only; prevalence is often a gap (3 lanes reported it missing in the first real run). Consider a dedicated prevalence query if the final report needs it reliably.

## Open questions for user
- (none right now; the emergency-behaviour question was answered 2026-10-20: pause and ask → built as 5.6)
- Rename the Python package `ai_decision_arena` → e.g. `health_arena` (and LangSmith project)? Mechanical but touches every import and the uv project name. Claude's suggestion: do it in Phase 8 before the API exists, or never.

## Progress log
- 2026-10-18: Phases 0–4 built and verified (technical version). Details in git history.
- 2026-10-20: **Pivot to health conditions.** Rewrote `schemas.py`, `state.py`, `config.py`, intake, clarification, planner, search, sources, extractor, research node; added `prompting.py`, `docs/pivot-medical.md`; updated all scripts, `.env.example`, README. Offline smoke test (fake Claude + Tavily, 29 LLM calls): full graph incl. one judge→research loop, all assertions passed.
- 2026-10-20: Real check (tracing off) — intake "I have diabetes" → 8 missing items, 0 red flags; clarification round 1 asked 6 questions (type/confirmation, duration, symptoms, treatments, other conditions/pregnancy, routine/goals); round 2 with answers → no more questions, facts merged into profile/symptoms/constraints, 6 explicit assumptions.
- 2026-10-20: Real `run_research.py` on the demo type-2 profile: 9 queries, 28 evidence (research 9 / doctor 9 / patient 10; 15 direct quotes, 1 downgraded), 8 rejected with reasons (duplicates, PCOS thread, wrong drug combination), 9 gaps (prevalence missing in all 3 lanes), 4 conflicts. Patient lane now yields real Reddit + Drugs.com reviews.
- 2026-10-20: Phase 5 built: proposer / critic / judge nodes + graph wiring + `run_debate.py` + `print_debate`. Real `run_debate.py` (tracing off, 134 s): 7 plans (research 3 / doctor 2 / patient 2), 7 criticisms (3–6 points each, mostly evidence-based), per-lane winners research_c 6.50 / doctor_a 6.00 / patient_a 5.83; patient lane judged insufficient (anecdotal) → verdict `request_clarification` with 4 required-evidence items. Plans were honest about gaps ("timeline: not covered by the evidence") and kept all medication decisions with the doctor.
- 2026-10-20: Fixes after the real run: (a) planner guarantees one prevalence/timeline query per lane on the first pass (prompt rule + Python fallback `_ensure_outlook_query`; verified with a real planner call: research & patient lanes complied, doctor lane got the fallback); (b) Judge asks ≤2 questions per lane only if the answer changes the winner, exact duplicates removed in Python; (c) follow-up research focus no longer depends on matching the Judge's question text.
- 2026-10-20: **5.4 verified by user.** `run_research.py`: 25 evidence (research 6 / doctor 14 / patient 5), 11 rejected with reasons, prevalence now covered in research+doctor lanes. `run_debate.py` (134 s): 8 plans, winners research_c 7.10 / doctor_a 6.95 / patient_b 5.35, patient lane insufficient → `request_clarification`, 3 Judge questions. `run_graph.py` with a type 1 scenario: 2 clarification rounds (round 2 triggered correctly by "type 1 + tablets only + lows"), research re-planned for type 1 (DKA, insulin, hypoglycaemia queries), verdict `proceed`, all three winners put urgent care / insulin review first. LangSmith: per-lane LLM runs nested under each node, 9 tavily_search under research, full run visible as a 3-turn thread (`revision_id 1d77869-dirty`).
- 2026-10-20: Fixes from 5.4: (1) clarification now returns `new_red_flags` and merges them into `red_flags`; CLI banner `print_red_flags`; real re-run of the user's round-2 answers captured the DKA-sign red flag. (2) Clarification prompt: screening questions ask "which of these" instead of yes/no lists (the user's "yes" to a 5-symptom list was ambiguous). (3) Extractor rejects title-only snippets (ev_010 in the type 1 run supported no claim). (4) Patient lane domains trimmed (see decisions).
- 2026-10-20: User ran the emergency scenario (type 1, tablets only, "all" DKA signs): screening question format worked ("Which of these do you have right now" → "all" → 6 symptoms recorded), red-flag banner shown, research and doctor lanes each produced ONE emergency-first plan (7.62 / 8.25), the patient lane's Proposer deliberately declined. Bug exposed: the Judge treated the declined lane as "no plans → more research" → second research pass (52 evidence) + second debate round → `insufficient_evidence` at the cap, with a misleading reason ("no usable evidence"). Fixed: `ProposerOutput.evidence_too_thin` + `proposer_lane_status` + Judge `declined` status (see decisions). Also: `run_graph.py` now streams progress and shows red flags immediately. Offline: full graph + declined/thin lane routes + streaming order verified.
- 2026-10-20: User ran a secondary-diabetes scenario ("other" type, 1 year, blurred vision, tablets, "deep breathing" in round 2). Verified: round 2 triggered by the ambiguous type; red-flag banner printed at 8 s, right after clarification and before research (streaming works); research 51 s / 24 evidence; proposer 21 s, critic 25 s, judge 11 s; total 108 s; research and patient lanes `declined`, doctor lane won with one emergency-first plan (7.05); verdict `proceed` with NO loop (declined-lane fix confirmed). Follow-ups: Proposer emergency rule (see decisions; verified with a real patient-lane call on cached research + injected red flags → one "Emergency first" plan, lane status ok), compound-question rule tightened.
- 2026-10-20: 5.5 built: `progress.py` + report() calls in intake, clarification, research (planner / per search / per extractor lane), proposer, critic, judge (per lane + decision); `stream_graph` in `print_helpers.py`; `run_graph.py`, `run_research.py`, `run_debate.py` all stream. Offline streaming test asserts progress lines appear BEFORE each node's ✔ line.
- 2026-10-20: User verified 5.5 live: `run_debate.py` showed per-lane `·` lines with real timings (proposer 28 s, critic 95 s cumulative, judge 116 s); `run_graph.py` ("not sure" type, tablets, deep breathing) showed the banner at 8 s, all three lanes returned "Emergency first" plans (7.42 / 7.85 / 7.00), verdict `proceed` with three winners. Exposed: the Judge still looped once (patient lane "insufficient") in an emergency → fixed with the no-loops-on-red-flags rule (offline-tested: insufficient lane + red flags → `insufficient_evidence`, no retry; all sufficient + red flags → `proceed`).
- 2026-10-20: User chose option 1 for emergencies (pause, human decides) and a SINGLE commit. 5.6 built: pause node + routes + statuses + CLI handling (`continue`/`stop`, stop prints a closing message and skips research/debate output). Offline tests: answers-revealed flags → pause (resume_to research) → invalid reply re-pauses with error → continue → no loop; stop → END `stopped_by_user` with nothing researched; intake-detected flags → pause BEFORE the clarification LLM runs → continue → questions → no second pause; streaming order incl. the pause.
- 2026-10-20: User tested the pause with "diabetes + vomiting + fast breathing": banner + pause at 5 s before any questions ✔, wrong reply "yes go" re-prompted with the error ✔, continue → questions ✔. Then answers revealed "chest" and the graph paused AGAIN ("2 times continue"): fixed → one decision per session; later flags only show. Offline test updated (new flag after continue → no second pause).
- 2026-10-20: User re-ran the emergency scenario after the pause-once fix: ONE pause (5 s, before questions), continue → 2 clarification rounds ("some" → asked which), later red flags (chest pain) printed only, research 66 s / 27 evidence, three "Emergency first" plans (7.10 / 7.30 / 7.30), `proceed`, no loop, ~2 min after continue. Critic findings used for two prompt tweaks in the Proposer emergency rule: never drive yourself (unconditional), don't anchor on one diagnosis (chest pain + fast breathing may be cardiac). 5.6 verified by user → ready for the single commit.

## ▶ Next step
**[YOU]** Make the SINGLE commit (everything since `1d77869`):
`Pivot to health perspectives: 3-lane research, debate nodes, live progress, red-flag pause`

Then **6.1 [CLAUDE]** Evidence Checker: verify the winning plans' claims against stored evidence (statuses verified / partially_supported / unsupported / contradicted / irrelevant / unavailable), record rejected evidence with reasons, route back to research on a material gap if retries remain (never when red flags are present), else continue with uncertainty.
