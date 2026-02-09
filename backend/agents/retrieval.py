"""
Retrieval Agent — Searches the local ChromaDB vector store for relevant cached knowledge.
First step in the retrieval-priority chain.
"""

import logging

from ..core.event_bus import EventBus
from ..core.llm_client import get_embedding
from ..core.vector_store import VectorStore

from ..config import SIMILARITY_THRESHOLD, VECTOR_SEARCH_TOP_K

logger = logging.getLogger(__name__)


async def run(
    query: str,
    event_bus: EventBus,
    vector_store: VectorStore,
    top_k: int = VECTOR_SEARCH_TOP_K,
    threshold: float = SIMILARITY_THRESHOLD,
) -> dict:
    """
    Search the vector DB for relevant cached knowledge.

    Returns:
        {
            "sufficient": bool,
            "results": [...],
            "best_score": float | None,
        }
    """
    await event_bus.agent_start("retrieval", "Searching local knowledge base...")

    try:
        # Embed the query
        query_embedding = await get_embedding(query)

        # Search all collections
        results = vector_store.search_all_collections(
            query_embedding=query_embedding,
            top_k=top_k,
        )

        if not results:
            await event_bus.agent_result(
                "retrieval",
                "No results found in vector DB",
                result_count=0,
            )
            return {"sufficient": False, "results": [], "best_score": None}

        best_distance = results[0]["distance"]
        sufficient = vector_store.has_sufficient_results(results, threshold)

        # Report results
        good_results = [r for r in results if r["distance"] <= threshold]
        await event_bus.agent_result(
            "retrieval",
            f"Found {len(results)} results, {len(good_results)} above threshold "
            f"(best distance: {best_distance:.3f}, threshold: {threshold})",
            result_count=len(results),
            good_count=len(good_results),
            best_distance=best_distance,
            sufficient=sufficient,
        )

        return {
            "sufficient": sufficient,
            "results": results,
            "best_score": best_distance,
            "query_embedding": query_embedding,
        }

    except Exception as e:
        logger.error(f"Retrieval agent error: {e}")
        await event_bus.agent_error("retrieval", f"Error: {e}")
        return {"sufficient": False, "results": [], "best_score": None}
