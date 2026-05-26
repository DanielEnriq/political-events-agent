"""AWS Bedrock implementation of LLMProvider.

Why this exists on Day 1 (even though it's not exercised until Day 5):
Civic uses Bedrock in production. Demonstrating that the provider swap is
a one-env-var change — not a code change — is one of the highest-signal
moves for the CTO conversation. The class below is structurally complete
and ready; only credentials are deferred to Day 5.

The class is **safe to construct without AWS credentials.** boto3's default
credential chain only resolves credentials when an API call is made, not
on client construction. So importing this module and instantiating the
provider will succeed; the first `call_structured()` call would fail with
a clear auth error if creds are missing.
"""

from __future__ import annotations

import os
from typing import TypeVar

from pydantic import BaseModel

from .provider import ModelAlias
from .structured import call_with_structured_output

T = TypeVar("T", bound=BaseModel)


# Bedrock model IDs use inference profiles (region-prefixed). The profile
# is the publicly published Sonnet 4.5 cross-region inference profile.
_ALIAS_TO_MODEL: dict[ModelAlias, str] = {
    "sonnet-main": "us.anthropic.claude-sonnet-4-5-20250929-v1:0",
    "sonnet-judge": "us.anthropic.claude-sonnet-4-5-20250929-v1:0",
    "haiku-fast": "us.anthropic.claude-haiku-4-5-20251001-v1:0",
}


class BedrockProvider:
    """Routes the same LLMProvider interface through AWS Bedrock."""

    name = "bedrock"

    def __init__(self, aws_region: str | None = None) -> None:
        # Imported lazily so the project doesn't require boto3 to be
        # installed unless Bedrock is actually used. (anthropic[bedrock]
        # pulls boto3; otherwise the import would fail. We surface a clear
        # error if so.)
        try:
            from anthropic import AnthropicBedrock  # type: ignore[attr-defined]
        except ImportError as e:
            raise RuntimeError(
                "anthropic.AnthropicBedrock is not available. Install the "
                "bedrock extra: `uv add 'anthropic[bedrock]'` (or pip equivalent)."
            ) from e

        region = aws_region or os.environ.get("AWS_REGION", "us-east-1")

        # AnthropicBedrock uses boto3 under the hood. Boto3 lazily resolves
        # creds on the first API call, so construction here is safe even
        # without AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY set. A
        # `call_structured()` call later will surface a clear auth error.
        self._client = AnthropicBedrock(aws_region=region)

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

        # call_with_structured_output works against AnthropicBedrock too:
        # it exposes the same .messages.create / .beta.messages interface.
        return call_with_structured_output(
            self._client,  # type: ignore[arg-type]
            model=model,
            system=system,
            user=user,
            output_schema=output_schema,
            temperature=temperature,
            max_tokens=max_tokens,
        )
