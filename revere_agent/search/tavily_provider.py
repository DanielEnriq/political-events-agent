"""Tavily implementation of SearchProvider.

Uses the `tavily-python` SDK. Two methods:
- `search(query)` returns lightweight hits (title, snippet, URL).
- `extract(urls)` returns longer, cleaner content for the URLs that
  passed Stage 4's quality bar and warrant deeper reading.

We use `search_depth='advanced'` for political queries (better recall on
nuanced topics, at modest extra cost) and `extract_depth='advanced'` only
for the small handful of URLs we choose to read in full.
"""

from __future__ import annotations

import os
from urllib.parse import urlparse

from tavily import TavilyClient

from revere_agent.schemas import ExtractedDoc, SearchHit


def _domain_of(url: str) -> str:
    try:
        return urlparse(url).netloc or ""
    except Exception:  # noqa: BLE001
        return ""


class TavilyProvider:
    name = "tavily"

    def __init__(self, api_key: str | None = None) -> None:
        key = api_key or os.environ.get("TAVILY_API_KEY")
        if not key:
            raise RuntimeError(
                "TAVILY_API_KEY is not set. Add it to your environment or "
                ".env file. (See .env.example.)"
            )
        self._client = TavilyClient(api_key=key)

    def search(
        self,
        query: str,
        *,
        max_results: int = 5,
        advanced: bool = True,
    ) -> list[SearchHit]:
        result = self._client.search(
            query=query,
            max_results=max_results,
            search_depth="advanced" if advanced else "basic",
            include_answer=False,
            include_raw_content=False,
        )
        hits: list[SearchHit] = []
        for r in result.get("results", []):
            url = r.get("url", "")
            hits.append(
                SearchHit(
                    url=url,
                    title=r.get("title", ""),
                    snippet=r.get("content", ""),  # Tavily calls it `content`
                    published_date=r.get("published_date"),
                    domain=_domain_of(url),
                    raw_score=r.get("score"),
                )
            )
        return hits

    def extract(
        self,
        urls: list[str],
        *,
        advanced: bool = True,
    ) -> list[ExtractedDoc]:
        if not urls:
            return []
        result = self._client.extract(
            urls=urls,
            extract_depth="advanced" if advanced else "basic",
        )
        docs: list[ExtractedDoc] = []
        for r in result.get("results", []):
            docs.append(
                ExtractedDoc(
                    url=r.get("url", ""),
                    raw_content=r.get("raw_content", ""),
                    extraction_depth="advanced" if advanced else "basic",
                )
            )
        return docs
