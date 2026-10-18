"""Pydantic models: the data contract shared by all agents.

Why Pydantic? A TypedDict only *describes* a dict. Pydantic *validates* it:
wrong types, missing fields or out-of-range numbers raise a ValidationError
instead of silently flowing into the next agent.

Field descriptions matter: in later steps Claude fills these models through
structured output, and the descriptions become part of its instructions.
"""

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl

# ---------------------------------------------------------------------------
# Fixed vocabularies (Literal = only these exact strings are allowed)
# ---------------------------------------------------------------------------

WorkflowStatus = Literal[
    "intake",
    "awaiting_clarification",
    "researching",
    "debating",
    "verifying",
    "awaiting_human_review",
    "reporting",
    "completed",
    "completed_with_uncertainty",
    "failed",
]

SourceType = Literal[
    "official_documentation",
    "benchmark_or_spec",          # official benchmarks, specs, release notes
    "github",                     # repos, issues, pull requests, discussions
    "community_discussion",       # Reddit, forums, Stack Overflow, ...
    "technical_article",          # engineering blogs, independent comparisons
    "other",
]

VerificationStatus = Literal[
    "pending",                    # not checked yet (set by Research)
    "verified",
    "partially_supported",
    "unsupported",
    "contradicted",
    "irrelevant",
    "unavailable",
]

JudgeDecision = Literal[
    "proceed",
    "request_more_research",
    "request_clarification",
    "insufficient_evidence",
]

HumanAction = Literal[
    "approve",
    "reject",
    "request_debate_round",
    "request_more_research",
    "modify_requirements",
    "add_context",
    "select_solution",
]

Level = Literal["low", "medium", "high"]

ProblemDomain = Literal[
    "backend_engineering",
    "databases",
    "ai_ml",
    "infrastructure_cloud",
    "devops",
    "security",
    "frontend",
    "software_architecture",
    "other",
]

EVIDENCE_ID_PATTERN = r"^ev_\d{3,}$"   # ev_001, ev_002, ...
SOLUTION_ID_PATTERN = r"^sol_[a-z]$"    # sol_a, sol_b, sol_c


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Intake
# ---------------------------------------------------------------------------

class NamedValue(BaseModel):
    """A name/value pair. Used instead of dict[str, str] because a fixed object shape
    works more reliably with structured output; the node converts the list to a dict."""

    name: str = Field(description='Short snake_case key, e.g. "expected_users", "cloud_provider".')
    value: str = Field(description="What the user said, kept close to their wording.")


class IntakeResult(BaseModel):
    """Output of the Intake node: the user's problem, normalized. Nothing invented."""

    is_technical_problem: bool = Field(description="False if the input is not a technical problem/decision.")
    problem_domain: ProblemDomain
    problem_summary: str = Field(description="One or two neutral sentences restating the problem. Do not add facts.")
    requirements: list[NamedValue] = Field(
        default_factory=list,
        description="Goals and needs the user EXPLICITLY stated (features, scale, workload, etc.). Never guess.",
    )
    constraints: list[NamedValue] = Field(
        default_factory=list,
        description="Limits the user EXPLICITLY stated (budget, cloud, team skills, deadlines, existing stack).",
    )
    missing_information: list[str] = Field(
        default_factory=list,
        max_length=8,
        description="Important unknowns that could change the recommendation.",
    )


# ---------------------------------------------------------------------------
# Clarification
# ---------------------------------------------------------------------------

class ClarificationResult(BaseModel):
    """Output of the Clarification node: do we need to ask the user something?"""

    need_clarification: bool = Field(description="True only if missing info could materially change the recommendation.")
    questions: list[str] = Field(default_factory=list, max_length=5, description="Concise, targeted questions. Empty if none.")
    reason: str = Field(description="Why these questions matter, or why no questions are needed.")


# ---------------------------------------------------------------------------
# Research evidence
# ---------------------------------------------------------------------------

class CommunityContext(BaseModel):
    """Extra detail for community sources (Reddit, forums, GitHub issues)."""

    issue_discussed: str = Field(description="The specific experience or problem being discussed.")
    is_recurring: bool = Field(description="True only if several independent people report it; False for a single anecdote.")
    context: str = Field(description="Setup in which it happened (scale, versions, environment).")
    workarounds: list[str] = Field(default_factory=list)
    relevant_to_user: bool


class Evidence(BaseModel):
    """One structured piece of research. Never fabricated: every field comes from a retrieved source."""

    evidence_id: str = Field(pattern=EVIDENCE_ID_PATTERN)
    source_title: str
    source_url: HttpUrl
    source_type: SourceType
    published_at: datetime | None = Field(default=None, description="Only if the source states it. Never guess.")
    retrieved_at: datetime = Field(default_factory=utc_now)
    relevant_excerpt: str = Field(max_length=2000, description="Short excerpt or faithful summary, not the whole page.")
    is_direct_quote: bool = Field(description="True if relevant_excerpt is copied verbatim, False if paraphrased.")
    claims_supported: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    community: CommunityContext | None = None
    relevance_score: float = Field(ge=0.0, le=1.0)
    reliability_notes: str = ""
    verification_status: VerificationStatus = "pending"


class ConflictingClaim(BaseModel):
    """Two or more evidence records that disagree."""

    topic: str
    evidence_ids: list[str] = Field(min_length=2)
    description: str


# ---------------------------------------------------------------------------
# Debate: Proposer → Critic → Judge
# ---------------------------------------------------------------------------

class CostEstimate(BaseModel):
    """Always an estimate unless pricing evidence was retrieved."""

    summary: str = Field(description='e.g. "~$50-150/month". Say "unknown" if there is no basis.')
    basis: str = Field(description="Usage levels and assumptions behind the number.")
    pricing_evidence_ids: list[str] = Field(default_factory=list)
    is_verified_price: bool = Field(default=False, description="True only when backed by retrieved pricing evidence.")


class Proposal(BaseModel):
    solution_id: str = Field(pattern=SOLUTION_ID_PATTERN)
    name: str
    description: str = Field(description="What it is and how it addresses the problem.")
    benefits: list[str]
    drawbacks: list[str]
    estimated_cost: CostEstimate
    assumptions: list[str]
    implementation_complexity: Level
    scalability_notes: str
    security_reliability_notes: str = ""
    supporting_evidence_ids: list[str] = Field(default_factory=list)
    evidence_gaps: list[str] = Field(default_factory=list)


class CriticismPoint(BaseModel):
    category: Literal[
        "technical_risk", "weak_assumption", "scalability", "performance", "security",
        "operational_complexity", "maintenance_cost", "vendor_lock_in", "failure_mode",
        "missing_requirement", "evidence_contradiction", "better_alternative",
    ]
    issue: str
    severity: Level
    basis: Literal["evidence", "engineering_judgment"] = Field(
        description="'evidence' only when backed by evidence_ids; otherwise 'engineering_judgment'."
    )
    is_verified_problem: bool = Field(description="True = demonstrated problem, False = possible risk.")
    evidence_ids: list[str] = Field(default_factory=list)
    suggested_improvement: str = ""


class Criticism(BaseModel):
    """The Critic's assessment of ONE proposal."""

    solution_id: str = Field(pattern=SOLUTION_ID_PATTERN)
    points: list[CriticismPoint]
    overall_assessment: str


class CriterionScore(BaseModel):
    criterion: str = Field(description='Rubric key, e.g. "requirements_fit".')
    score: float = Field(ge=0, le=10)
    explanation: str


class SolutionScore(BaseModel):
    """The Judge's scores for ONE proposal. weighted_total is computed in Python, not by the LLM."""

    solution_id: str = Field(pattern=SOLUTION_ID_PATTERN)
    criterion_scores: list[CriterionScore]
    weighted_total: float | None = Field(default=None, ge=0, le=10)
    key_benefits: list[str]
    key_drawbacks: list[str]
    confidence: Level
    confidence_reason: str
    supporting_evidence_ids: list[str] = Field(default_factory=list)
    remaining_risks: list[str] = Field(default_factory=list)


class Verdict(BaseModel):
    """The Judge's routing decision. Drives the conditional edge after the Judge node."""

    decision: JudgeDecision
    reason: str
    winning_solution_id: str | None = Field(default=None, pattern=SOLUTION_ID_PATTERN)
    required_evidence: list[str] = Field(default_factory=list, description="What Research should look for next.")
    clarification_questions: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Verification, human review, report, errors
# ---------------------------------------------------------------------------

class ClaimVerification(BaseModel):
    """Evidence Checker result for one factual claim."""

    claim: str
    solution_id: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    status: VerificationStatus
    notes: str = Field(description="Why this status. For rejected evidence, the reason it was rejected.")
    is_anecdotal: bool = False


class HumanReviewInput(BaseModel):
    """What the user sends back at the Human Review pause. Validated before routing."""

    action: HumanAction
    feedback: str = Field(default="", max_length=4000)
    selected_solution_id: str | None = Field(default=None, pattern=SOLUTION_ID_PATTERN)
    requirement_changes: dict[str, str] = Field(default_factory=dict)


class EvidenceRef(BaseModel):
    evidence_id: str
    title: str
    url: HttpUrl
    verification_status: VerificationStatus


class FinalReport(BaseModel):
    original_problem: str
    confirmed_requirements: dict[str, str]
    clarifications: dict[str, str]
    research_methodology: str
    recommended_solution_id: str | None = Field(description="None when no defensible winner exists.")
    recommendation_summary: str
    is_conditional: bool = Field(description="True if the recommendation depends on unconfirmed assumptions.")
    alternatives: list[Proposal]
    scores: list[SolutionScore]
    key_evidence: list[EvidenceRef]
    critic_key_objections: list[str]
    considerations: dict[str, str] = Field(default_factory=dict, description="security / scalability / performance / maintenance")
    uncertainties: list[str]
    unsupported_claims: list[str]
    unresolved_questions: list[str]
    next_steps: list[str]


class ErrorRecord(BaseModel):
    """Safe error info. Never put API keys or full request payloads here."""

    node: str
    operation: str
    category: Literal["rate_limit", "timeout", "invalid_llm_output", "search_failed", "database", "invalid_input", "unknown"]
    message: str = Field(max_length=500)
    retry_count: int = 0
    recoverable: bool
    occurred_at: datetime = Field(default_factory=utc_now)
