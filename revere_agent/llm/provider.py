"""LLMProvider Protocol — the abstraction Civic cares about most.

WHY THIS EXISTS
---------------
Civic uses AWS Bedrock in production. We build with the direct Anthropic API
for iteration speed, but the project must be one env-var swap away from
Bedrock. The Protocol defines the only surface the rest of the codebase
talks to; concrete providers implement it.

Equally important: the rest of the codebase never sees a concrete model ID
like `claude-sonnet-4-5-20250929`. It sees a logical alias like
`sonnet-main`. Each provider resolves aliases to its own ID space. That
means swapping providers is a config change, never a code change.
"""

from typing import Protocol, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)

# Logical aliases the stages refer to. Concrete provider implementations
# resolve these to provider-specific model IDs.
ModelAlias = str

# Default aliases. Adding a new alias only requires updating each provider's
# resolver — call sites stay unchanged.
DEFAULT_ALIASES: tuple[ModelAlias, ...] = (
    "sonnet-main",   # the workhorse for analysis stages
    "sonnet-judge",  # held separate so we can later use a different model for judging
    "haiku-fast",    # for cheap stages (none in Day 1 plan)
)


class LLMProvider(Protocol):
    """The only LLM surface stages may use."""

    name: str  # 'anthropic' | 'bedrock' — useful for trace metadata

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
        """Call the model and return a Pydantic-validated instance of output_schema.

        Implementations must guarantee the return value passes Pydantic
        validation. How they get there (native structured outputs, forced
        tool-use, JSON mode) is their concern.
        """
        ...
