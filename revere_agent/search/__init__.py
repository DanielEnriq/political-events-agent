"""Search provider abstraction. Tavily is the default."""

from .provider import SearchProvider
from .tavily_provider import TavilyProvider


def make_search_provider_from_env() -> SearchProvider:
    """Construct the default search provider. Currently Tavily only; the
    abstraction is in place to swap Brave / Exa / SerpAPI / Perplexity later.
    """
    return TavilyProvider()


__all__ = ["SearchProvider", "TavilyProvider", "make_search_provider_from_env"]
