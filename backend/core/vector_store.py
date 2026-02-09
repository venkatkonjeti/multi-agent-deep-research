"""
Vector Store — ChromaDB manager for persistent local vector storage.
Manages three collections: research_cache, ingested_documents, web_knowledge.
"""
from __future__ import annotations

import logging
import time
import uuid

import chromadb
from chromadb.config import Settings

from ..config import (
    CHROMA_DB_DIR,
    COLLECTION_RESEARCH_CACHE,
    COLLECTION_INGESTED_DOCS,
    COLLECTION_WEB_KNOWLEDGE,
    VECTOR_SEARCH_TOP_K,
    SIMILARITY_THRESHOLD,
)

logger = logging.getLogger(__name__)

# Singleton client
_chroma_client: chromadb.PersistentClient | None = None


def get_chroma_client() -> chromadb.PersistentClient:
    global _chroma_client
    if _chroma_client is None:
        _chroma_client = chromadb.PersistentClient(
            path=CHROMA_DB_DIR,
            settings=Settings(anonymized_telemetry=False),
        )
    return _chroma_client


def _get_or_create_collection(name: str) -> chromadb.Collection:
    client = get_chroma_client()
    return client.get_or_create_collection(
        name=name,
        metadata={"hnsw:space": "cosine"},
    )


# ─── Public API ──────────────────────────────────────────────

class VectorStore:
    """Unified interface for all vector DB operations."""

    def __init__(self):
        self.research_cache = _get_or_create_collection(COLLECTION_RESEARCH_CACHE)
        self.ingested_docs = _get_or_create_collection(COLLECTION_INGESTED_DOCS)
        self.web_knowledge = _get_or_create_collection(COLLECTION_WEB_KNOWLEDGE)

    def _collection_by_name(self, name: str) -> chromadb.Collection:
        return {
            COLLECTION_RESEARCH_CACHE: self.research_cache,
            COLLECTION_INGESTED_DOCS: self.ingested_docs,
            COLLECTION_WEB_KNOWLEDGE: self.web_knowledge,
        }[name]

    # ─── Add documents ───────────────────────────────────────

    def add_documents(
        self,
        collection_name: str,
        texts: list[str],
        embeddings: list[list[float]],
        metadatas: list[dict] | None = None,
        ids: list[str] | None = None,
    ) -> None:
        """Add documents with pre-computed embeddings to a collection."""
        collection = self._collection_by_name(collection_name)
        if ids is None:
            ids = [str(uuid.uuid4()) for _ in texts]
        if metadatas is None:
            metadatas = [{"timestamp": time.time()} for _ in texts]
        else:
            for m in metadatas:
                m.setdefault("timestamp", time.time())

        # ChromaDB batch limit is 5461
        batch_size = 5000
        for i in range(0, len(texts), batch_size):
            collection.add(
                ids=ids[i : i + batch_size],
                documents=texts[i : i + batch_size],
                embeddings=embeddings[i : i + batch_size],
                metadatas=metadatas[i : i + batch_size],
            )
        logger.info(
            f"Added {len(texts)} documents to '{collection_name}'"
        )

    # ─── Search ──────────────────────────────────────────────

    def search(
        self,
        collection_name: str,
        query_embedding: list[float],
        top_k: int = VECTOR_SEARCH_TOP_K,
        where: dict | None = None,
    ) -> list[dict]:
        """
        Search a collection by embedding similarity.
        Returns list of {text, metadata, distance, id}.
        """
        collection = self._collection_by_name(collection_name)
        kwargs = {
            "query_embeddings": [query_embedding],
            "n_results": top_k,
            "include": ["documents", "metadatas", "distances"],
        }
        if where:
            kwargs["where"] = where

        try:
            results = collection.query(**kwargs)
        except Exception as e:
            logger.error(f"Vector search error in '{collection_name}': {e}")
            return []

        docs = results.get("documents", [[]])[0]
        metas = results.get("metadatas", [[]])[0]
        dists = results.get("distances", [[]])[0]
        ids = results.get("ids", [[]])[0]

        return [
            {
                "text": doc,
                "metadata": meta,
                "distance": dist,
                "id": doc_id,
            }
            for doc, meta, dist, doc_id in zip(docs, metas, dists, ids)
        ]

    def search_all_collections(
        self,
        query_embedding: list[float],
        top_k: int = VECTOR_SEARCH_TOP_K,
    ) -> list[dict]:
        """Search across all three collections, merge and sort by distance."""
        all_results = []
        for name in [
            COLLECTION_RESEARCH_CACHE,
            COLLECTION_INGESTED_DOCS,
            COLLECTION_WEB_KNOWLEDGE,
        ]:
            results = self.search(name, query_embedding, top_k=top_k)
            for r in results:
                r["collection"] = name
            all_results.extend(results)
        # Sort by distance ascending (lower = more similar in cosine)
        all_results.sort(key=lambda x: x["distance"])
        return all_results[:top_k]

    def has_sufficient_results(
        self,
        results: list[dict],
        threshold: float = SIMILARITY_THRESHOLD,
        min_results: int = 1,
    ) -> bool:
        """Check if search results meet the confidence threshold."""
        good_results = [r for r in results if r["distance"] <= threshold]
        return len(good_results) >= min_results

    # ─── Cache a research Q&A pair ───────────────────────────

    def cache_research(
        self,
        query: str,
        answer: str,
        query_embedding: list[float],
        sources: list[str] | None = None,
    ) -> None:
        """Store a Q&A pair in research_cache for future retrieval."""
        metadata = {
            "query": query[:500],
            "sources": ", ".join(sources or []),
            "timestamp": time.time(),
            "content_type": "research_qa",
        }
        self.add_documents(
            collection_name=COLLECTION_RESEARCH_CACHE,
            texts=[f"Q: {query}\n\nA: {answer}"],
            embeddings=[query_embedding],
            metadatas=[metadata],
        )

    # ─── Stats ───────────────────────────────────────────────

    def get_stats(self) -> dict:
        """Return document counts per collection."""
        return {
            COLLECTION_RESEARCH_CACHE: self.research_cache.count(),
            COLLECTION_INGESTED_DOCS: self.ingested_docs.count(),
            COLLECTION_WEB_KNOWLEDGE: self.web_knowledge.count(),
        }
