"""
Search Engine — DuckDuckGo web search wrapper.
No API key required. Returns structured search results.
"""

import logging

from duckduckgo_search import DDGS

from ..config import WEB_SEARCH_MAX_RESULTS

logger = logging.getLogger(__name__)


async def search_web(
    query: str,
    max_results: int = WEB_SEARCH_MAX_RESULTS,
) -> list[dict]:
    """
    Search the web using DuckDuckGo.
    Returns list of {title, url, snippet}.
    """
    try:
        results = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=max_results):
                results.append({
                    "title": r.get("title", ""),
                    "url": r.get("href", r.get("link", "")),
                    "snippet": r.get("body", r.get("snippet", "")),
                })
        logger.info(f"Web search for '{query}': {len(results)} results")
        return results
    except Exception as e:
        logger.error(f"Web search failed for '{query}': {e}")
        return []


async def search_news(
    query: str,
    max_results: int = WEB_SEARCH_MAX_RESULTS,
) -> list[dict]:
    """Search DuckDuckGo news."""
    try:
        results = []
        with DDGS() as ddgs:
            for r in ddgs.news(query, max_results=max_results):
                results.append({
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "snippet": r.get("body", ""),
                    "date": r.get("date", ""),
                    "source": r.get("source", ""),
                })
        return results
    except Exception as e:
        logger.error(f"News search failed: {e}")
        return []
