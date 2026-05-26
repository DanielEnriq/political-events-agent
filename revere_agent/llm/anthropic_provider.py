"""Direct Anthropic API implementation of LLMProvider.

This is the default during development for iteration speed. The Bedrock
provider is structurally identical, differing only in client construction
and the model-alias → model-ID mapping.
"""

from __future__ import annotations

import os
from typing import TypeVar

from anthropic import Anthropic
from pydantic import BaseModel

from .provider import ModelAlias
from .structured import call_with_structured_output

T = TypeVar("T", bound=BaseModel)


# Logical alias → concrete Anthropic model ID.
# Keeping this mapping inside the provider means stage code never names a
# concrete model — provider swap = config change, not code change.
_ALIAS_TO_MODEL: dict[ModelAlias, str] = {
    "sonnet-main": "claude-sonnet-4-5",
    "sonnet-judge": "claude-sonnet-4-5",
    "haiku-fast": "claude-haiku-4-5",
}


class AnthropicProvider:
    """Calls Anthropic's hosted API directly."""

    name = "anthropic"

    def __init__(self, api_key: str | None = None) -> None:
        key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set. Add it to your environment "
                "or .env file. (See .env.example.)"
            )
        # The SDK is lazy about network; constructing the client never calls out.
        self._client = Anthropic(api_key=key)

    def call_structured(
        self,
        *,
        system: str,
        user: str,
        output_schema: type[T],
        model_alias: ModelAlias = "sonnet-main",
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> T:
        model = _ALIAS_TO_MODEL.get(model_alias)
        if model is None:
            raise KeyError(
                f"Unknown model alias '{model_alias}'. "
                f"Known: {sorted(_ALIAS_TO_MODEL)}"
            )

        return call_with_structured_output(
            self._client,
            model=model,
            system=system,
            user=user,
            output_schema=output_schema,
            temperature=temperature,
            max_tokens=max_tokens,
        )
