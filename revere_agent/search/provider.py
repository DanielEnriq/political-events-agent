"""SearchProvider Protocol.

Mirrors the same swappable-abstraction principle as LLMProvider. Tavily is
the default for this project (per the candidacy prompt), but the surface
below is generic enough to swap Brave, Exa, SerpAPI, Perplexity, or
internal Civic retrievers — without touching agent code.

The provider is intentionally dumb: it does retrieval. All quality reasoning
(authority, slant, primary/secondary) happens in Stage 4, where Claude
reasons about what came back.
"""

from typing import Protocol

from revere_agent.schemas import ExtractedDoc, SearchHit


class SearchProvider(Protocol):
    name: str

    def search(
        self,
        query: str,
        *,
        max_results: int = 5,
        advanced: bool = True,
    ) -> list[SearchHit]:
        """Return up to `max_results` hits for the query."""
        ...

    def extract(
        self,
        urls: list[str],
        *,
        advanced: bool = True,
    ) -> list[ExtractedDoc]:
        """Return the full(er) content of each URL."""
        ...
