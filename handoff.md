# AI Decision Arena — Handoff

> **Read this first in every new session.** It records the plan, how we work, what's done, and what's next.

## How we work (agreed workflow)
- We build in **small steps**. One step finishes → we check it → we move on.
- Each step is tagged **[YOU]** (user does it, sends a screenshot) or **[CLAUDE]** (Claude implements it).
- Before each [CLAUDE] step, Claude explains briefly: **what** it will build, **why**, **how**, and **prerequisites** to understand it.
- Claude asks questions when something is unclear instead of guessing.
- After each step, update the **Progress Log** and **Next Step** sections below.
- Goal is **learning** as well as a working app — prefer simple, readable code first, then add features.

## Project summary
A multi-agent system that helps users make technical decisions. Instead of one LLM answer, agents
clarify the problem → research the web → propose 2–3 solutions → critique → judge/score → verify
evidence → let the human review → write a final evidence-backed report.

Full original requirements: see `docs/requirements.md` (user pastes it in Step 0.1).

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

## Graph design (11 nodes)
```
START → intake → clarification ──(need_clarification? interrupt & loop, max 2)──┐
                      │ no                                                       │
                      ▼                                                          │
                  research ◄──────────── (judge/checker: more research, max 2 retries)
                      ▼
                  proposer → critic → judge ──(request_clarification)──► clarification
                                        │ proceed / insufficient_evidence
                                        ▼
                               evidence_checker
                                        ▼
                                 human_review (interrupt) ──(revise / more research / new round, bounded)
                                        │ approve
                                        ▼
                                  final_report → completion → END

Any node failure → error_recovery → (retry same node | completion with status=failed)
```
Loop limits: debate rounds ≤ 2, research retries ≤ 2 (first pass isn't a retry), clarification rounds ≤ 2.

## Implementation plan (small steps)

### Phase 0 — Setup
- [ ] 0.1 [YOU] Paste the full project requirements into `docs/requirements.md`. Create API keys: Anthropic, Tavily, LangSmith. (Don't send keys to Claude!)
- [ ] 0.2 [CLAUDE] Project skeleton: `backend/` with uv, `pyproject.toml`, `.env.example`, `.gitignore`.
- [ ] 0.3 [YOU] Copy `.env.example` → `.env`, fill keys, run `uv sync`. Screenshot.
- [ ] 0.4 [CLAUDE] `check_env.py` script that pings Claude/Tavily/LangSmith. [YOU] run it, screenshot.

### Phase 1 — LangGraph basics (learning)
- [ ] 1.1 [CLAUDE] "Hello graph": tiny State + 2 dummy nodes, run it, **print graph** (ASCII + Mermaid PNG).
- [ ] 1.2 [CLAUDE] One node calls Claude. [YOU] run it.
- [ ] 1.3 [YOU] Open LangSmith, find the trace, screenshot.

### Phase 2 — Real state & schemas
- [ ] 2.1 [CLAUDE] `ArenaState` TypedDict + Pydantic models (Evidence, Proposal, Criticism, Score, Verdict, Report).
- [ ] 2.2 [CLAUDE] Config (limits, rubric weights, model name) via pydantic-settings.

### Phase 3 — Intake + Clarification (human-in-the-loop)
- [ ] 3.1 [CLAUDE] Intake node (structured output from Claude).
- [ ] 3.2 [CLAUDE] Clarification node with `interrupt()` + InMemorySaver; CLI script to answer & resume.
- [ ] 3.3 [YOU] Run CLI, answer questions, screenshot trace showing interrupt/resume.

### Phase 4 — Research
- [ ] 4.1 [CLAUDE] Tavily client wrapper + query generation.
- [ ] 4.2 [CLAUDE] Convert results → structured Evidence records (dedupe, limits, untrusted-content handling).

### Phase 5 — Debate
- [ ] 5.1 [CLAUDE] Proposer agent.
- [ ] 5.2 [CLAUDE] Critic agent.
- [ ] 5.3 [CLAUDE] Judge agent + weighted rubric + routing (more research / clarification / proceed).

### Phase 6 — Verification & finishing nodes
- [ ] 6.1 [CLAUDE] Evidence Checker + routing.
- [ ] 6.2 [CLAUDE] Human Review node (interrupt, validated actions).
- [ ] 6.3 [CLAUDE] Final Report + Completion nodes.
- [ ] 6.4 [CLAUDE] Error Recovery node + retries/backoff.
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
- [ ] 9.2 [CLAUDE] Problem input + clarification screens.
- [ ] 9.3 [CLAUDE] Agent activity, evidence panel, comparison view.
- [ ] 9.4 [CLAUDE] Human review, final report, feedback.

### Phase 10 — Quality
- [ ] 10.1 [CLAUDE] Unit tests (mocked Claude/Tavily) + graph tests.
- [ ] 10.2 [CLAUDE] Eval dataset + LangSmith evaluation.
- [ ] 10.3 [CLAUDE] README (install, run, test, troubleshoot).

## Decisions log
- 2026-10-18: Start with InMemorySaver for learning, switch to Postgres in Phase 7 (requirement: Postgres for final).
- 2026-10-18: Sequential graph for MVP (no parallel nodes yet).
- 2026-10-18: Use git for this project (local repo first; GitHub optional later).

## Open questions for user
- Which Claude model? (cheaper/faster Sonnet vs stronger Opus) — default proposal: Sonnet for most agents, configurable.

## Progress log
- 2026-10-18: Created `handoff.md` with plan.
- 2026-10-18: Git setup started — G1 [YOU] set git name/email, G2 [CLAUDE] `git init` + `.gitignore`, G3 first commit.

## ▶ Next step
**0.1 [YOU]** Paste requirements into `docs/requirements.md`; create API keys (Anthropic, Tavily, LangSmith) and keep them private. Then answer the open questions.
