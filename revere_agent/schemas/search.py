"""Search-related schemas: the plan (Stage 3) and the raw hits/extractions
returned by SearchProvider implementations.

The search-result types live here rather than in search/models.py so that
all stage contracts are findable in one place (revere_agent.schemas).
"""

from typing import Literal

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
]


class SearchPlan(BaseModel):
    """Stage 3 output: whether to search, and what to search for."""

    model_config = StrictModel

    needs_search: bool = Field(
        description="True only if the model lacks sufficient confidence to "
        "answer from its own knowledge."
    )
    rationale: str = Field(
        description="Why search is or isn't needed. Reference specificity, "
        "freshness, and the model's own confidence."
    )
    queries: list[str] = Field(
        default_factory=list,
        max_length=3,
        description="0 to 3 targeted search queries. Empty if needs_search is false.",
    )
    target_source_types: list[SourceType] = Field(
        default_factory=list,
        description="Which kinds of sources we ideally want — guides downstream "
        "source-quality reasoning.",
    )
    why_model_knowledge_insufficient: str | None = Field(
        default=None,
        description="If needs_search is true, name the specific knowledge gap.",
    )


class SearchHit(BaseModel):
    """A single search result as returned by SearchProvider.search()."""

    model_config = StrictModel

    url: str
    title: str
    snippet: str
    published_date: str | None = None
    domain: str
    raw_score: float | None = Field(
        default=None,
        description="Provider-native relevance score, if available (Tavily returns one).",
    )


class ExtractedDoc(BaseModel):
    """Full-content extraction of a URL via SearchProvider.extract()."""

    model_config = StrictModel

    url: str
    raw_content: str
    extraction_depth: Literal["basic", "advanced"]
