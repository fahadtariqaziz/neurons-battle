"""All app settings in one typed place.

Every value has a safe default and can be overridden from backend/.env or a real
environment variable with the same name in UPPER_CASE, e.g. MAX_DEBATE_ROUNDS=3.

Usage:
    from ai_decision_arena.config import get_settings
    settings = get_settings()
    settings.max_debate_rounds
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_FILE = Path(__file__).resolve().parents[2] / ".env"   # backend/.env

# Copy .env into os.environ too: LangChain/LangSmith/Tavily read their keys from there.
# Real environment variables win over .env (override=False).
load_dotenv(ENV_FILE, override=False)

# Judge rubric: criterion -> weight. The descriptions are shown to the Judge verbatim.
DEFAULT_RUBRIC = {
    "fit_to_user": 0.30,
    "safety": 0.25,
    "evidence_quality": 0.20,
    "practicality": 0.15,
    "completeness": 0.10,
}
RUBRIC_DESCRIPTIONS = {
    "fit_to_user": "Matches THIS user's condition, profile, symptoms, goals and constraints (diet, budget, preferences).",
    "safety": "Avoids harm: respects contraindications, interactions, red flags; never suggests stopping prescribed treatment.",
    "evidence_quality": "Backed by relevant, strong, recent evidence (guidelines/trials > references > anecdotes), with few gaps.",
    "practicality": "Realistic to follow day to day given the user's situation (effort, cost, access).",
    "completeness": "Covers routine, diet, medications/treatments, expected timeline and prevalence/outlook.",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILE, extra="ignore")

    # --- secrets (SecretStr prints as '**********', so keys never leak into logs) ---
    anthropic_api_key: SecretStr
    tavily_api_key: SecretStr
    langsmith_api_key: SecretStr | None = None

    # --- Claude ---
    anthropic_model: str = "claude-sonnet-5-5"
    llm_max_tokens: int = Field(default=4000, ge=256, le=32000)
    llm_timeout_seconds: float = Field(default=90, gt=0)
    llm_max_retries: int = Field(default=2, ge=0, le=5, description="Retries for API errors and invalid structured output.")

    # --- loop limits (see handoff.md for what each counter means) ---
    max_clarification_rounds: int = Field(default=2, ge=0, le=5)
    max_research_retries: int = Field(default=2, ge=0, le=5)
    max_debate_rounds: int = Field(default=2, ge=1, le=5)

    # --- research limits (cost control). Research runs 3 lanes: research / doctor / patient ---
    queries_per_perspective: int = Field(default=3, ge=1, le=6)
    max_results_per_query: int = Field(default=5, ge=1, le=20)
    max_hits_per_perspective: int = Field(default=12, ge=3, le=30, description="Hits sent to the extractor per lane.")
    max_evidence_per_perspective: int = Field(default=10, ge=1, le=30)
    max_excerpt_chars: int = Field(default=2000, ge=200, le=2000)   # Evidence.relevant_excerpt max_length
    tavily_search_depth: Literal["basic", "advanced"] = "basic"      # advanced = better snippets, 2x credits
    tavily_patient_search_depth: Literal["basic", "advanced"] = "advanced"   # forum snippets are short with basic
    tavily_timeout_seconds: float = Field(default=30, gt=0)
    search_max_retries: int = Field(default=2, ge=0, le=5, description="Retries per query for transient Tavily errors.")

    # --- judge rubric: criterion -> weight; must add up to 1.0 ---
    # Override in .env as JSON: RUBRIC_WEIGHTS={"fit_to_user":0.4,...}
    rubric_weights: dict[str, float] = Field(default_factory=lambda: dict(DEFAULT_RUBRIC))

    # --- tracing ---
    langsmith_tracing: bool = True
    langsmith_project: str = "ai-decision-arena"

    # --- infrastructure (used from Phase 7/8) ---
    database_url: str = "postgresql://postgres:password@localhost:5432/ai_decision_arena"
    frontend_url: str = "http://localhost:3000"
    backend_url: str = "http://localhost:8000"

    @field_validator("rubric_weights")
    @classmethod
    def weights_must_sum_to_one(cls, weights: dict[str, float]) -> dict[str, float]:
        if not weights:
            raise ValueError("rubric_weights must not be empty")
        if any(w < 0 for w in weights.values()):
            raise ValueError("rubric weights must be >= 0")
        total = sum(weights.values())
        if abs(total - 1.0) > 0.001:
            raise ValueError(f"rubric weights must add up to 1.0 (got {total:.3f})")
        return weights


@lru_cache
def get_settings() -> Settings:
    """Build Settings once and reuse it (lru_cache = remember the first result)."""
    return Settings()
