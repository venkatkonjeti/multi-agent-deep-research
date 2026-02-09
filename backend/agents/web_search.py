"""
Web Search Agent — Searches the web, extracts content, and stores in vector DB.
Used when vector DB and model knowledge are insufficient.
"""

import asyncio
import logging

from ..core.event_bus import EventBus
from ..core.llm_client import get_embeddings_batch
from ..core.vector_store import VectorStore
from ..core.chunker import chunk_text
from ..tools.search_engine import search_web
from ..tools.web_scraper import scrape_url

from ..config import (
    COLLECTION_WEB_KNOWLEDGE,
    WEB_SEARCH_MAX_RESULTS,
)

logger = logging.getLogger(__name__)


async def run(
    query: str,
    event_bus: EventBus,
    vector_store: VectorStore,
) -> dict:
    """
    Search the web, extract content, store in vector DB.

    Returns:
        {
            "success": bool,
            "results": [{"title", "url", "content"}],
            "stored_count": int,
        }
    """
    await event_bus.agent_start("web_search", "Searching the web via DuckDuckGo...")

    try:
        # Step 1: Search
        search_results = await search_web(query, max_results=WEB_SEARCH_MAX_RESULTS)

        if not search_results:
            await event_bus.agent_result(
                "web_search", "No web results found", result_count=0
            )
            return {"success": False, "results": [], "stored_count": 0}

        await event_bus.agent_progress(
            "web_search",
            f"Found {len(search_results)} results, extracting content...",
            urls=[r["url"] for r in search_results],
        )

        # Step 2: Scrape content from top results
        enriched_results = []
        for sr in search_results:
            url = sr.get("url", "")
            if not url:
                continue
            try:
                scraped = await scrape_url(url)
                if scraped["success"] and scraped["content"]:
                    enriched_results.append({
                        "title": scraped.get("title") or sr.get("title", ""),
                        "url": url,
                        "content": scraped["content"],
                        "snippet": sr.get("snippet", ""),
                    })
            except Exception as e:
                logger.warning(f"Failed to scrape {url}: {e}")

        if not enriched_results:
            # Fall back to snippets only
            enriched_results = [
                {
                    "title": sr.get("title", ""),
                    "url": sr.get("url", ""),
                    "content": sr.get("snippet", ""),
                    "snippet": sr.get("snippet", ""),
                }
                for sr in search_results
                if sr.get("snippet")
            ]

        await event_bus.agent_progress(
            "web_search",
            f"Extracted content from {len(enriched_results)} pages, storing in vector DB...",
        )

        # Step 3: Chunk, embed, and store in vector DB
        all_texts = []
        all_metas = []
        for result in enriched_results:
            chunks = chunk_text(result["content"])
            for i, chunk in enumerate(chunks):
                all_texts.append(chunk)
                all_metas.append({
                    "query": query[:500],
                    "source_url": result["url"],
                    "title": result["title"][:200],
                    "chunk_index": i,
                    "content_type": "web_search",
                })

        stored_count = 0
        if all_texts:
            embeddings = await get_embeddings_batch(all_texts)
            vector_store.add_documents(
                collection_name=COLLECTION_WEB_KNOWLEDGE,
                texts=all_texts,
                embeddings=embeddings,
                metadatas=all_metas,
            )
            stored_count = len(all_texts)

        await event_bus.agent_result(
            "web_search",
            f"Stored {stored_count} chunks from {len(enriched_results)} web pages",
            result_count=len(enriched_results),
            stored_count=stored_count,
        )

        return {
            "success": True,
            "results": enriched_results,
            "stored_count": stored_count,
        }

    except Exception as e:
        logger.error(f"Web search agent error: {e}")
        await event_bus.agent_error("web_search", f"Error: {e}")
        return {"success": False, "results": [], "stored_count": 0}
