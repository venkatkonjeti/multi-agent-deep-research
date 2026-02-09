"""
Orchestrator Agent — Central router and decision engine.
Implements the full retrieval-priority chain:
  1. Check vector DB → if sufficient, answer from cache
  2. Query model knowledge → if confident, answer + cache
  3. Fall back to web search → answer + cache

Also handles URL ingestion and PDF upload routing.
"""
from __future__ import annotations

import asyncio
import logging
import re
from typing import AsyncGenerator

from ..core.event_bus import EventBus
from ..core.vector_store import VectorStore
from . import retrieval, knowledge, web_search, ingestion, synthesis

logger = logging.getLogger(__name__)

# URL pattern for detecting URLs in user messages
_URL_PATTERN = re.compile(
    r"https?://[^\s<>\"'\]\)]+",
    re.IGNORECASE,
)


def _classify_intent(message: str) -> str:
    """
    Classify user intent.
    Returns: 'url_ingestion', 'question'
    """
    urls = _URL_PATTERN.findall(message)
    if urls:
        # Check if the message is primarily a URL (ingestion intent)
        stripped = message.strip()
        for url in urls:
            stripped = stripped.replace(url, "").strip()
        # If little text remains besides the URL, it's ingestion
        remaining_words = stripped.split()
        ingestion_keywords = {
            "read", "ingest", "process", "analyze", "summarize",
            "learn", "store", "save", "index", "load", "add",
        }
        if len(remaining_words) <= 5 or any(
            w.lower() in ingestion_keywords for w in remaining_words
        ):
            return "url_ingestion"
    return "question"


async def handle_query(
    query: str,
    event_bus: EventBus,
    vector_store: VectorStore,
    conversation_history: list[dict] | None = None,
    conversation_id: str = "",
) -> AsyncGenerator[str, None]:
    """
    Main entry point. Routes the user query through the agent pipeline.
    Yields tokens for streaming the final response.
    """
    intent = _classify_intent(query)

    await event_bus.plan_step(
        f"Classified intent as: {intent.upper()}",
        intent=intent,
    )

    if intent == "url_ingestion":
        async for token in _handle_url_ingestion(
            query, event_bus, vector_store, conversation_id
        ):
            yield token
        return

    # ─── QUESTION FLOW ───────────────────────────────────────
    async for token in _handle_question(
        query, event_bus, vector_store, conversation_history
    ):
        yield token


async def _handle_url_ingestion(
    query: str,
    event_bus: EventBus,
    vector_store: VectorStore,
    conversation_id: str,
) -> AsyncGenerator[str, None]:
    """Handle URL ingestion intent."""
    urls = _URL_PATTERN.findall(query)

    for url in urls:
        await event_bus.plan_step(f"Ingesting URL: {url}")
        result = await ingestion.ingest_url(
            url=url,
            event_bus=event_bus,
            vector_store=vector_store,
            conversation_id=conversation_id,
        )

        if result["success"]:
            msg = (
                f"✅ **Content ingested successfully!**\n\n"
                f"- **Source:** [{result.get('title', url)}]({url})\n"
                f"- **Chunks stored:** {result['chunks_stored']}\n\n"
                f"You can now ask me questions about this content."
            )
        else:
            msg = (
                f"❌ **Failed to ingest URL:** {url}\n\n"
                f"Error: {result.get('error', 'Unknown error')}"
            )

        for token in msg:
            await event_bus.stream_token(token)
            yield token

    await event_bus.stream_end()


async def _handle_question(
    query: str,
    event_bus: EventBus,
    vector_store: VectorStore,
    conversation_history: list[dict] | None,
) -> AsyncGenerator[str, None]:
    """
    Handle question intent with the full retrieval-priority chain:
      Step 1: Vector DB search
      Step 2: Model knowledge (if vector DB insufficient)
      Step 3: Web search (if model not confident)
      Synthesis: Merge all results and stream answer
    """

    # ═══════════════════════════════════════════════════════════
    # STEP 1: Retrieval Agent — Check Vector DB
    # ═══════════════════════════════════════════════════════════
    await event_bus.plan_step("Step 1: Searching local vector database...")

    retrieval_result = await retrieval.run(
        query=query,
        event_bus=event_bus,
        vector_store=vector_store,
    )

    query_embedding = retrieval_result.get("query_embedding")

    if retrieval_result["sufficient"]:
        # Vector DB has good results — synthesize from cached knowledge
        await event_bus.plan_step(
            "✅ Sufficient knowledge found in vector DB. Generating answer from cache."
        )

        async for token in synthesis.run(
            query=query,
            event_bus=event_bus,
            vector_store=vector_store,
            vector_results=retrieval_result["results"],
            conversation_history=conversation_history,
            query_embedding=query_embedding,
        ):
            yield token
        return

    # ═══════════════════════════════════════════════════════════
    # STEP 2: Knowledge Agent — Query model directly
    # ═══════════════════════════════════════════════════════════
    await event_bus.plan_step(
        "Step 2: Vector DB insufficient. Querying model knowledge..."
    )

    knowledge_result = await knowledge.run(
        query=query,
        event_bus=event_bus,
        conversation_history=conversation_history,
    )

    if knowledge_result["confident"]:
        # Model is confident — synthesize with model knowledge + any partial vector results
        await event_bus.plan_step(
            "✅ Model provided confident response. Generating synthesized answer."
        )

        async for token in synthesis.run(
            query=query,
            event_bus=event_bus,
            vector_store=vector_store,
            vector_results=retrieval_result.get("results"),
            knowledge_response=knowledge_result["response"],
            conversation_history=conversation_history,
            query_embedding=query_embedding,
        ):
            yield token
        return

    # ═══════════════════════════════════════════════════════════
    # STEP 3: Web Search Agent — Search the web
    # ═══════════════════════════════════════════════════════════
    await event_bus.plan_step(
        "Step 3: Model not confident. Searching the web for additional knowledge..."
    )

    web_result = await web_search.run(
        query=query,
        event_bus=event_bus,
        vector_store=vector_store,
    )

    # ═══════════════════════════════════════════════════════════
    # SYNTHESIS: Merge all sources
    # ═══════════════════════════════════════════════════════════
    await event_bus.plan_step(
        "Synthesizing answer from all sources (vector DB + model + web)..."
    )

    async for token in synthesis.run(
        query=query,
        event_bus=event_bus,
        vector_store=vector_store,
        vector_results=retrieval_result.get("results"),
        knowledge_response=knowledge_result.get("response"),
        web_results=web_result.get("results"),
        conversation_history=conversation_history,
        query_embedding=query_embedding,
    ):
        yield token


async def handle_pdf_upload(
    file_path: str,
    filename: str,
    event_bus: EventBus,
    vector_store: VectorStore,
    conversation_id: str = "",
) -> dict:
    """Handle PDF file upload — delegates to the ingestion agent."""
    await event_bus.plan_step(f"Processing uploaded PDF: {filename}")

    result = await ingestion.ingest_pdf(
        file_path=file_path,
        filename=filename,
        event_bus=event_bus,
        vector_store=vector_store,
        conversation_id=conversation_id,
    )

    return result
