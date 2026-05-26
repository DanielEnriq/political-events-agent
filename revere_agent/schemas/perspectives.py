"""PerspectiveAnalysis — output of Stage 5 (multi-perspective synthesis).

Implements Anthropic's "Ideological Turing Test" framing: each perspective
must be written as a proponent would endorse it. Schema enforces equal depth
(same number of core_claims per perspective is a soft norm; equality is
checked at eval time).
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

StrictModel = ConfigDict(extra="forbid")

DisputeKind = Literal["empirical", "normative", "mixed"]


class Perspective(BaseModel):
    model_config = StrictModel

    label: str = Field(
        description="A short, neutral label for this perspective "
        "(e.g. 'border-enforcement-first', 'humanitarian-access-first'). "
        "Avoid partisan labels where a substantive one exists."
    )
    core_claims: list[str] = Field(
        description="The main things proponents of this view assert."
    )
    strongest_evidence: list[str] = Field(
        description="The strongest evidence proponents would point to."
    )
    key_concerns_about_other_views: list[str] = Field(
        description="What proponents see as the weaknesses of opposing views."
    )
    representative_sources: list[str] = Field(
        default_factory=list,
        description="URLs from the evidence base that exemplify this perspective.",
    )
    steelman_quality_self_assessment: str = Field(
        description="Brief self-critique: would a proponent of this view "
        "recognize and endorse the framing above?"
    )


class PerspectiveAnalysis(BaseModel):
    model_config = StrictModel

    perspectives: list[Perspective] = Field(
        description="Major perspectives on the question. Usually 2; sometimes "
        "3+ when there are meaningful sub-positions."
    )
    areas_of_consensus: list[str] = Field(
        default_factory=list,
        description="Facts or framings most perspectives accept.",
    )
    areas_of_disagreement: list[str] = Field(
        default_factory=list,
        description="The specific points of contention.",
    )
    empirical_vs_normative: dict[str, DisputeKind] = Field(
        default_factory=dict,
        description="Map of disagreement -> kind. 'Tax cuts increased "
        "revenue' is empirical; 'tax cuts are good policy' is normative.",
    )
