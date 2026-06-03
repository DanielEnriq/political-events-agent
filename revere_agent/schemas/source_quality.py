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
    "reference",
    "encyclopedia",
    "nonprofit_reference",
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


class EvidenceCoverage(BaseModel):
    """Structured coverage judgment emitted by S4.

    S4 populates this after assessing all retrieved sources. EvidenceSufficiency
    consumes these typed booleans directly, eliminating domain heuristics and
    gap-text keyword scanning from deterministic code.
    """

    model_config = StrictModel

    has_primary_sources: bool = Field(
        description=(
            "True if any retrieved source qualifies as a primary, government, "
            "or court record — i.e., an original or official document rather "
            "than a secondary summary."
        )
    )
    has_court_sources: bool = Field(
        description=(
            "True if any retrieved source is a court opinion, filing, or "
            "official court document."
        )
    )
    has_government_sources: bool = Field(
        description=(
            "True if any retrieved source is an official government publication, "
            "agency page, or legislative record."
        )
    )
    perspective_coverage_asymmetric: bool = Field(
        description=(
            "True if the retrieved evidence clearly favours one side of the "
            "debate — i.e., one perspective has strong source support while "
            "another lacks retrieved evidence."
        )
    )
    asymmetry_note: str | None = Field(
        default=None,
        description=(
            "Brief description of which perspective or side lacks retrieved "
            "source support. Populate only when perspective_coverage_asymmetric "
            "is True."
        ),
    )


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
    coverage: EvidenceCoverage | None = Field(
        default=None,
        description=(
            "Structured coverage flags produced by S4. When present, "
            "EvidenceSufficiency uses these typed fields instead of domain "
            "heuristics or gap-text keyword scanning."
        ),
    )
