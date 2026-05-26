"""SourceAssessment + EvidenceBase — output of Stage 4 (source-quality reasoning).

The model scores each retrieved source on five axes WITH a reasoning string
per axis, not a number alone. Slant is surfaced as a transparency act, not
used to discount the source.
"""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

StrictModel = ConfigDict(extra="forbid")

SourceType = Literal[
    "primary",
    "government",
    "court",
    "mainstream_news",
    "think_tank",
    "academic",
    "polling",
    "blog",
    "unknown",
]

EditorialSlant = Literal[
    "left",
    "center_left",
    "center",
    "center_right",
    "right",
    "unclear",
    "n/a_primary",
]

PrimacyTier = Literal["primary", "secondary", "tertiary"]


class SourceAssessment(BaseModel):
    """Per-source structured judgment."""

    model_config = StrictModel

    url: str
    source_type: SourceType
    authority_reasoning: str = Field(
        description="Why this source is or isn't authoritative for this query."
    )
    recency_assessment: str = Field(
        description="How current the source is relative to the event in question."
    )
    likely_editorial_slant: EditorialSlant
    slant_evidence: str = Field(
        description="Why you placed it there. Transparency, not a filter."
    )
    primary_vs_secondary: PrimacyTier
    relevance_to_query: Annotated[int, Field(ge=1, le=5)]
    confidence_in_source: Annotated[int, Field(ge=1, le=5)]


class EvidenceBase(BaseModel):
    """Aggregate of all source assessments + cross-source reasoning."""

    model_config = StrictModel

    assessments: list[SourceAssessment]
    confidence_in_evidence: Annotated[int, Field(ge=1, le=5)] = Field(
        description="Overall confidence based on corroboration across sources."
    )
    conflicting_claims: list[str] = Field(
        default_factory=list,
        description="Claims where sources disagree.",
    )
    gaps: list[str] = Field(
        default_factory=list,
        description="What we still don't know after retrieval.",
    )
