"""IntakeAnalysis — output of Stage 1 (intake & context normalization)."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# Why `extra="forbid"`: Anthropic's structured outputs require
# `additionalProperties: false` at every level of the JSON Schema. Setting
# this on every model means Pydantic emits it for free, and tool-use also
# benefits because it removes ambiguity for the model.
StrictModel = ConfigDict(extra="forbid")

Modality = Literal[
    "factual",
    "opinion",
    "explanation",
    "procedural",
    "conversational_filler",
    "multi_part",
]


class IntakeAnalysis(BaseModel):
    """Self-contained restatement and classification of the user's message."""

    model_config = StrictModel

    canonical_query: str = Field(
        description="The user's message rewritten as a self-contained question. "
        "Resolve pronouns ('that ruling', 'it') using conversation history."
    )
    modality: Modality = Field(
        description="What kind of request the user is making."
    )
    user_stated_stance: str | None = Field(
        default=None,
        description="If the user expressed a political stance, paraphrase it "
        "neutrally. Otherwise null.",
    )
    multi_turn_dependency: bool = Field(
        description="True if interpreting the message requires prior turns."
    )
    notes: str = Field(
        description="Brief observations downstream stages should know about."
    )
