"""Shared Claude access for every agent.

Two kinds of failure, two kinds of retry:
1. API errors (rate limit, timeout, 5xx): the Anthropic SDK retries them itself
   with exponential backoff, up to `llm_max_retries` times (ChatAnthropic.max_retries).
2. Invalid structured output (fails Pydantic validation): call_structured() shows
   Claude the validation error and asks again, up to `llm_max_retries` times.
   If the output was cut off at max_tokens, it asks for a shorter answer instead
   (without re-sending the truncated text).
If both are exhausted, the error is raised for the graph's Error Recovery node.

In a quick (patient chat) session the model comes from settings.quick_model and every system prompt
gets QUICK_MODE_NOTE: shorter answers are the main lever for speed (output tokens take the time).
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


QUICK_MODE_NOTE = """
Speed mode (a patient is waiting for this): keep every text field to one short sentence, keep lists to at
most 3 items, and when the instructions give a range (e.g. "5-6 questions") use the lower end. A QUICK SESSION
rule in the instructions overrides this note."""


def get_llm(max_tokens: int | None = None, model: str | None = None) -> ChatAnthropic:
    """The client for the active session mode (see config.session_mode); `model` overrides the mode's model."""
    settings = get_settings()
    return _client(model or settings.anthropic_model, max_tokens or settings.llm_max_tokens,
                   settings.llm_timeout_seconds, settings.llm_max_retries)


@lru_cache
def _client(model: str, max_tokens: int, timeout: float, max_retries: int) -> ChatAnthropic:
    """One ChatAnthropic client per combination, reused across calls."""
    return ChatAnthropic(
        model=model,
        api_key=get_settings().anthropic_api_key,  # SecretStr is accepted directly
        max_tokens=max_tokens,
        timeout=timeout,
        max_retries=max_retries,                   # SDK backoff for transient API errors
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
    if settings.session_mode == "quick":
        system_prompt += "\n" + QUICK_MODE_NOTE
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

        raw = result["raw"]
        if raw.response_metadata.get("stop_reason") == "max_tokens":
            # Output was cut off. Re-sending the truncated text wastes tokens: just ask for less.
            last_error = "output truncated at max_tokens"
            messages = messages + [HumanMessage(content=(
                "Your previous answer was cut off because it was too long. "
                f"Return the complete {schema.__name__} again, much more concisely: "
                "shorter texts, fewer items, only what matters most."
            ))]
            continue

        # Validation failed: show Claude its own answer plus the exact error, then retry.
        last_error = str(result["parsing_error"])[:1000]
        messages = messages + [
            raw,
            HumanMessage(content=(
                f"Your previous output was invalid:\n{last_error}\n\n"
                f"Return a corrected {schema.__name__} that satisfies every constraint."
            )),
        ]

    raise LLMOutputError(schema.__name__, attempts, last_error)
