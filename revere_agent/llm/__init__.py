"""LLM provider abstraction and concrete implementations."""

from .anthropic_provider import AnthropicProvider
from .bedrock_provider import BedrockProvider
from .provider import DEFAULT_ALIASES, LLMProvider, ModelAlias


def make_provider_from_env() -> LLMProvider:
    """Construct the provider chosen by the PROVIDER env var.

    PROVIDER=anthropic (default) → AnthropicProvider
    PROVIDER=bedrock → BedrockProvider

    This is the single switch the rest of the codebase uses. Swapping
    Civic-style (Bedrock) for dev-style (direct Anthropic) is one env var.
    """
    import os

    choice = os.environ.get("PROVIDER", "anthropic").lower()
    if choice == "anthropic":
        return AnthropicProvider()
    if choice == "bedrock":
        return BedrockProvider()
    raise ValueError(
        f"Unknown PROVIDER='{choice}'. Set PROVIDER=anthropic or PROVIDER=bedrock."
    )


__all__ = [
    "AnthropicProvider",
    "BedrockProvider",
    "DEFAULT_ALIASES",
    "LLMProvider",
    "ModelAlias",
    "make_provider_from_env",
]
