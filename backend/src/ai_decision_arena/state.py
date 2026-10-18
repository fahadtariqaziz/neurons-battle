"""ArenaState: the shared state that flows through the LangGraph graph.

Design rules:
- Each field has ONE owner node that writes it (see comments). Other nodes only read it.
- Nested items are stored as plain dicts (Pydantic model.model_dump(mode="json")).
  Plain JSON keeps checkpoints in PostgreSQL simple and readable, and the API can
  return them directly. Nodes re-validate with Model.model_validate(d) when reading.
- No raw web pages here: only short, structured Evidence records.
- No reducers yet: the MVP graph is sequential, so only one node writes at a time.
"""

from typing import TypedDict

from ai_decision_arena.schemas import HumanAction, WorkflowStatus


class ArenaState(TypedDict, total=False):
    # --- session ---------------------------------------------------- (API / intake)
    thread_id: str
    status: WorkflowStatus               # editor warns on typos like "complete"
    current_node: str                    # last node that ran, for the frontend

    # --- problem understanding ----------------------------------------- (intake)
    question: str                        # the user's original text, never rewritten
    user_context: str                    # optional extra context from the form
    problem_domain: str                  # a ProblemDomain value, e.g. "databases"
    problem_summary: str                 # neutral restatement (used for research queries)
    requirements: dict[str, str]         # e.g. {"workload": "read-heavy"}
    constraints: dict[str, str]          # e.g. {"cloud": "AWS", "budget": "< $200/mo"}
    missing_information: list[str]

    # --- clarification ------------------------------------------ (clarification)
    need_clarification: bool
    clarification_questions: list[str]   # questions currently pending
    clarification_reason: str            # Claude's reason for asking / not asking
    clarification_answers: dict[str, str]  # question -> user's answer (all rounds)
    assumptions: list[str]               # recorded when we stop asking
    clarification_round_count: int       # one user-input round = +1 (not per question)

    # --- research ----------------------------------------------------- (research)
    research_queries: list[str]
    evidence: list[dict]                 # Evidence
    research_summary: str
    evidence_gaps: list[str]
    conflicting_claims: list[dict]       # ConflictingClaim
    rejected_sources: list[dict]         # {url, title, reason}: kept for transparency
    research_retry_count: int            # +1 only when going BACK to research (first pass = 0)

    # --- debate ------------------------------------------- (proposer/critic/judge)
    proposals: list[dict]                # Proposal                 (proposer)
    criticisms: list[dict]               # Criticism                (critic)
    scores: list[dict]                   # SolutionScore            (judge)
    verdict: dict                        # Verdict                  (judge)
    debate_round: int                    # +1 each time the proposer starts a new round

    # --- verification ------------------------------------------ (evidence_checker)
    verification_results: list[dict]     # ClaimVerification

    # --- human review ---------------------------------------------- (human_review)
    human_action: HumanAction
    user_feedback: str

    # --- output ------------------------------------------- (final_report/completion)
    final_report: dict                   # FinalReport
    unresolved_questions: list[str]

    # --- errors ------------------------------------------------ (error_recovery)
    error: dict | None                   # ErrorRecord
    failed_node: str                     # which node to retry after recovery
