"""FinalResponse + SelfCheckReport — output of Stage 7.

Stage 7 combines composition and a constitutional-AI-style critique-and-
revise loop in a single LLM call. The SelfCheckReport documents whether
each of the six Anthropic-derived political principles was satisfied and
what was revised.
"""

from pydantic import BaseModel, ConfigDict, Field

StrictModel = ConfigDict(extra="forbid")


class Citation(BaseModel):
    model_config = StrictModel

    label: str
    url: str
    used_for_claim: str = Field(
        description="The specific claim in the response this citation supports."
    )


class SelfCheckReport(BaseModel):
    """Self-evaluation against the six Anthropic political principles.

    Source for the principles: Anthropic, "Measuring political bias in
    Claude" (Nov 13, 2025). https://www.anthropic.com/news/political-even-handedness
    """

    model_config = StrictModel

    avoided_unsolicited_opinion: bool
    factually_accurate_and_comprehensive: bool
    steelmanned_each_perspective: bool
    neutral_terminology_used: bool
    equal_depth_across_perspectives: bool
    respectful_tone: bool
    revisions_made: list[str] = Field(
        default_factory=list,
        description="Concrete changes made between draft and final, "
        "tied to which principle motivated each change.",
    )


class FinalResponse(BaseModel):
    model_config = StrictModel

    response_text: str = Field(
        description="The text shown to the user. Plain prose with citations "
        "inline in markdown-link style [label](url) where appropriate."
    )
    citations: list[Citation] = Field(default_factory=list)
    neutrality_self_check: SelfCheckReport
    residual_uncertainty: str = Field(
        description="What the user should know is still uncertain after this response."
    )
    suggested_followups: list[str] = Field(
        default_factory=list,
        description="2-3 followup questions the user might find useful.",
    )
