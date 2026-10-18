"""Shared Claude access for every agent.

Two kinds of failure, two kinds of retry:
1. API errors (rate limit, timeout, 5xx): the Anthropic SDK retries them itself
   with exponential backoff, up to `llm_max_retries` times (ChatAnthropic.max_retries).
2. Invalid structured output (fails Pydantic validation): call_structured() shows
   Claude the validation error and asks again, up to `llm_max_retries` times.
If both are exhausted, the error is raised for the graph's Error Recovery node.
"""

from functools import lru_cache
from typing import TypeVar

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from pydantic import BaseModel

from ai_decision_arena.config import get_settings

T = TypeVar("T", bound=BaseModel)


class LLMOutputError(Exception):
    """Claude's output still failed validation after all retries."""

    def __init__(self, schema_name: str, attempts: int, last_error: str):
        self.schema_name = schema_name
        self.attempts = attempts
        self.last_error = last_error
        super().__init__(f"{schema_name}: invalid output after {attempts} attempt(s): {last_error}")


@lru_cache
def get_llm(max_tokens: int | None = None) -> ChatAnthropic:
    """One ChatAnthropic client per max_tokens value, reused across calls."""
    settings = get_settings()
    return ChatAnthropic(
        model=settings.anthropic_model,
        api_key=settings.anthropic_api_key,       # SecretStr is accepted directly
        max_tokens=max_tokens or settings.llm_max_tokens,
        timeout=settings.llm_timeout_seconds,
        max_retries=settings.llm_max_retries,     # SDK backoff for transient API errors
    )


def call_structured(
    schema: type[T],
    system_prompt: str,
    user_content: str,
    *,
    max_tokens: int | None = None,
    run_name: str | None = None,
) -> T:
    """Ask Claude to fill `schema` and return a validated instance of it.

    Raises LLMOutputError if the output is still invalid after the retry budget.
    """
    settings = get_settings()
    structured_llm = get_llm(max_tokens).with_structured_output(
        schema,
        method="json_schema",   # Anthropic native structured outputs
        include_raw=True,       # return errors instead of raising, so we can retry
    )
    messages: list[BaseMessage] = [SystemMessage(content=system_prompt), HumanMessage(content=user_content)]
    attempts = settings.llm_max_retries + 1
    last_error = ""

    for attempt in range(1, attempts + 1):
        result = structured_llm.invoke(
            messages,
            config={"run_name": run_name or schema.__name__, "metadata": {"attempt": attempt}},
        )
        if result["parsed"] is not None:
            return result["parsed"]

        # Validation failed: show Claude its own answer plus the exact error, then retry.
        last_error = str(result["parsing_error"])[:1000]
        messages = messages + [
            result["raw"],
            HumanMessage(content=(
                f"Your previous output was invalid:\n{last_error}\n\n"
                f"Return a corrected {schema.__name__} that satisfies every constraint."
            )),
        ]

    raise LLMOutputError(schema.__name__, attempts, last_error)
