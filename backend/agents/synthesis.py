"""
Synthesis Agent — Merges results from all sources, generates the final answer,
streams it token-by-token, and caches the result in the vector DB.
"""
from __future__ import annotations

import logging
from typing import AsyncGenerator

from ..core.event_bus import EventBus
from ..core.llm_client import chat_stream, get_embedding
from ..core.vector_store import VectorStore

from ..config import MAX_CONTEXT_LENGTH, INFERENCE_MODEL

logger = logging.getLogger(__name__)

_SYNTHESIS_PROMPT = """You are a deep research assistant. Synthesize a comprehensive answer to the user's question using ALL the provided sources.

RULES:
1. Use information from ALL provided sources to build a thorough response.
2. If sources contain diagrams or image descriptions, describe them clearly and offer to explain further.
3. Cite which source each piece of information comes from (e.g., [Vector DB], [Model Knowledge], [Web: title]).
4. If sources conflict, note the discrepancy.
5. Format your answer with markdown: use headers, bullet points, tables, code blocks as appropriate.
6. If the question is about a diagram or visual, describe it in detail and recreate it in text/ASCII/mermaid if possible.
7. Be thorough but don't pad with filler.

SOURCES:
{sources}

USER QUESTION: {query}

Provide a comprehensive, well-sourced answer:"""


def _build_source_context(
    vector_results: list[dict] | None = None,
    knowledge_response: str | None = None,
    web_results: list[dict] | None = None,
) -> tuple[str, list[str]]:
    """
    Build the source context string and list of source labels.
    Returns (context_str, source_labels).
    """
    parts = []
    sources = []
    remaining = MAX_CONTEXT_LENGTH

    # Vector DB results
    if vector_results:
        for r in vector_results:
            collection = r.get("collection", "cache")
            label = f"[Vector DB: {collection}]"
            text = r.get("text", "")[:1000]
            entry = f"{label}\n{text}\n"
            if len(entry) <= remaining:
                parts.append(entry)
                remaining -= len(entry)
                source_url = r.get("metadata", {}).get("source_url", "")
                sources.append(source_url or collection)

    # Model knowledge
    if knowledge_response:
        entry = f"[Model Knowledge ({INFERENCE_MODEL})]\n{knowledge_response[:2000]}\n"
        if len(entry) <= remaining:
            parts.append(entry)
            remaining -= len(entry)
            sources.append("model_knowledge")

    # Web search results
    if web_results:
        for wr in web_results:
            title = wr.get("title", "Web")
            url = wr.get("url", "")
            content = wr.get("content", wr.get("snippet", ""))[:1500]
            label = f"[Web: {title}]"
            entry = f"{label}\nURL: {url}\n{content}\n"
            if len(entry) <= remaining:
                parts.append(entry)
                remaining -= len(entry)
                sources.append(url or title)

    return "\n---\n".join(parts), sources


async def run(
    query: str,
    event_bus: EventBus,
    vector_store: VectorStore,
    vector_results: list[dict] | None = None,
    knowledge_response: str | None = None,
    web_results: list[dict] | None = None,
    conversation_history: list[dict] | None = None,
    query_embedding: list[float] | None = None,
) -> AsyncGenerator[str, None]:
    """
    Synthesize the final answer from all sources.
    Yields tokens for streaming. After streaming completes, caches the result.
    """
    await event_bus.agent_start("synthesis", "Merging sources and generating answer...")

    source_context, source_labels = _build_source_context(
        vector_results=vector_results,
        knowledge_response=knowledge_response,
        web_results=web_results,
    )

    if not source_context:
        source_context = "No external sources available. Answer based on your knowledge."
        source_labels = ["model_knowledge"]

    # Build messages
    messages = []
    if conversation_history:
        messages.extend(conversation_history[-6:])

    prompt = _SYNTHESIS_PROMPT.format(sources=source_context, query=query)
    messages.append({"role": "user", "content": prompt})

    await event_bus.agent_progress(
        "synthesis",
        f"Generating response from {len(source_labels)} sources...",
        sources=source_labels[:10],
    )

    # Stream the response
    full_response = ""
    try:
        async for token in chat_stream(messages=messages, temperature=0.5):
            full_response += token
            await event_bus.stream_token(token)
            yield token

        await event_bus.stream_end()

        # Cache the Q&A in vector DB
        try:
            if query_embedding is None:
                query_embedding = await get_embedding(query)

            vector_store.cache_research(
                query=query,
                answer=full_response,
                query_embedding=query_embedding,
                sources=source_labels,
            )
            await event_bus.agent_result(
                "synthesis",
                "Answer generated and cached in vector DB",
                response_length=len(full_response),
                sources=source_labels[:10],
                cached=True,
            )
        except Exception as e:
            logger.warning(f"Failed to cache research result: {e}")
            await event_bus.agent_result(
                "synthesis",
                "Answer generated (caching failed)",
                response_length=len(full_response),
                cached=False,
            )

    except Exception as e:
        logger.error(f"Synthesis agent error: {e}")
        await event_bus.agent_error("synthesis", f"Error generating answer: {e}")
        error_msg = f"I encountered an error while generating the response: {e}"
        yield error_msg
