"""
LLM Client — Unified inference layer.
Embeddings go directly to OpenAI. Chat and vision use Ollama as primary
with automatic OpenAI fallback on 500 / rate-limit / load failures.
"""
from __future__ import annotations

import base64
import logging
from typing import AsyncGenerator

import ollama
from openai import AsyncOpenAI, APIStatusError, RateLimitError

from ..config import (
    OLLAMA_BASE_URL,
    INFERENCE_MODEL,
    OPENAI_API_KEY,
    OPENAI_INFERENCE_MODEL,
    OPENAI_EMBEDDING_MODEL,
    OPENAI_VISION_MODEL,
)

logger = logging.getLogger(__name__)

# ─── Singleton clients ──────────────────────────────────────
_ollama_client: ollama.AsyncClient | None = None
_openai_client: AsyncOpenAI | None = None


def get_client() -> ollama.AsyncClient:
    """Get or create the singleton async Ollama client."""
    global _ollama_client
    if _ollama_client is None:
        _ollama_client = ollama.AsyncClient(host=OLLAMA_BASE_URL)
    return _ollama_client


def _get_openai_client() -> AsyncOpenAI:
    """Get or create the singleton async OpenAI client."""
    global _openai_client
    if _openai_client is None:
        if not OPENAI_API_KEY:
            raise RuntimeError(
                "OpenAI fallback triggered but OPENAI_API_KEY is not set. "
                "Set it via environment variable or in config.py."
            )
        _openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY)
    return _openai_client


def _is_retriable(exc: Exception) -> bool:
    """Should we retry this Ollama error with OpenAI?"""
    msg = str(exc).lower()
    # Ollama ResponseError with status 500 / model-load failures
    if isinstance(exc, ollama.ResponseError):
        if getattr(exc, "status_code", 0) in (500, 429, 503):
            return True
        if "failed to load" in msg or "resource" in msg:
            return True
    # Generic connection / timeout
    if any(k in msg for k in ("connection", "timeout", "refused", "rate limit", "429")):
        return True
    return False


# ═══════════════════════════════════════════════════════════
#  Embeddings — OpenAI direct (Ollama embedding disabled)
# ═══════════════════════════════════════════════════════════

async def get_embedding(text: str) -> list[float]:
    """Generate an embedding vector for a single text string (OpenAI)."""
    client = _get_openai_client()
    resp = await client.embeddings.create(
        model=OPENAI_EMBEDDING_MODEL,
        input=text,
    )
    return resp.data[0].embedding


async def get_embeddings_batch(texts: list[str]) -> list[list[float]]:
    """Generate embeddings for a batch of texts (OpenAI)."""
    client = _get_openai_client()
    resp = await client.embeddings.create(
        model=OPENAI_EMBEDDING_MODEL,
        input=texts,
    )
    return [item.embedding for item in resp.data]


# ═══════════════════════════════════════════════════════════
#  Chat (non-streaming)
# ═══════════════════════════════════════════════════════════

async def chat(
    messages: list[dict],
    model: str = INFERENCE_MODEL,
    temperature: float = 0.7,
) -> str:
    """Send a chat request and return the full response text."""
    try:
        client = get_client()
        response = await client.chat(
            model=model,
            messages=messages,
            options={"temperature": temperature},
        )
        return response["message"]["content"]
    except Exception as exc:
        if _is_retriable(exc):
            logger.warning("Ollama chat failed (%s), falling back to OpenAI", exc)
            return await _openai_chat(messages, temperature)
        raise


async def _openai_chat(
    messages: list[dict],
    temperature: float = 0.7,
) -> str:
    """OpenAI fallback for non-streaming chat."""
    client = _get_openai_client()
    # Convert Ollama-style messages (may have "images" key) to OpenAI format
    oai_messages = _convert_messages_for_openai(messages)
    resp = await client.chat.completions.create(
        model=OPENAI_INFERENCE_MODEL,
        messages=oai_messages,
        temperature=temperature,
    )
    return resp.choices[0].message.content or ""


# ═══════════════════════════════════════════════════════════
#  Chat (streaming)
# ═══════════════════════════════════════════════════════════

async def chat_stream(
    messages: list[dict],
    model: str = INFERENCE_MODEL,
    temperature: float = 0.7,
) -> AsyncGenerator[str, None]:
    """Stream chat response token-by-token. Tries Ollama, falls back to OpenAI."""
    try:
        client = get_client()
        stream = await client.chat(
            model=model,
            messages=messages,
            stream=True,
            options={"temperature": temperature},
        )
        async for chunk in stream:
            token = chunk["message"]["content"]
            if token:
                yield token
        return  # success — exit generator
    except Exception as exc:
        if not _is_retriable(exc):
            raise
        logger.warning("Ollama stream failed (%s), falling back to OpenAI", exc)

    # OpenAI streaming fallback
    async for token in _openai_chat_stream(messages, temperature):
        yield token


async def _openai_chat_stream(
    messages: list[dict],
    temperature: float = 0.7,
) -> AsyncGenerator[str, None]:
    """OpenAI fallback for streaming chat."""
    client = _get_openai_client()
    oai_messages = _convert_messages_for_openai(messages)
    stream = await client.chat.completions.create(
        model=OPENAI_INFERENCE_MODEL,
        messages=oai_messages,
        temperature=temperature,
        stream=True,
    )
    async for chunk in stream:
        delta = chunk.choices[0].delta
        if delta.content:
            yield delta.content


# ═══════════════════════════════════════════════════════════
#  Vision (multimodal)
# ═══════════════════════════════════════════════════════════

async def describe_image(
    image_bytes: bytes,
    prompt: str = "Describe this image in detail including all text, labels, structure, relationships, and data flows visible.",
) -> str:
    """Send an image to a vision model and get a textual description."""
    b64_image = base64.b64encode(image_bytes).decode("utf-8")
    try:
        client = get_client()
        response = await client.chat(
            model=INFERENCE_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                    "images": [b64_image],
                }
            ],
        )
        return response["message"]["content"]
    except Exception as exc:
        if _is_retriable(exc):
            logger.warning("Ollama vision failed (%s), falling back to OpenAI", exc)
            return await _openai_describe_image(b64_image, prompt)
        raise


async def _openai_describe_image(b64_image: str, prompt: str) -> str:
    """OpenAI fallback for vision / image description."""
    client = _get_openai_client()
    resp = await client.chat.completions.create(
        model=OPENAI_VISION_MODEL,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{b64_image}",
                            "detail": "high",
                        },
                    },
                ],
            }
        ],
        max_tokens=1024,
    )
    return resp.choices[0].message.content or ""


# ═══════════════════════════════════════════════════════════
#  Message format converter
# ═══════════════════════════════════════════════════════════

def _convert_messages_for_openai(messages: list[dict]) -> list[dict]:
    """Convert Ollama-style messages to OpenAI API format.

    Ollama puts images under msg["images"] as base64 strings.
    OpenAI expects multimodal content as a list of content parts.
    """
    converted = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        images = msg.get("images", [])

        if images:
            parts: list[dict] = [{"type": "text", "text": content}]
            for img_b64 in images:
                parts.append({
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/png;base64,{img_b64}",
                        "detail": "high",
                    },
                })
            converted.append({"role": role, "content": parts})
        else:
            converted.append({"role": role, "content": content})
    return converted


# ═══════════════════════════════════════════════════════════
#  Health Check
# ═══════════════════════════════════════════════════════════

async def check_health() -> dict:
    """Check Ollama connectivity and available models."""
    result: dict = {}
    # Ollama (chat / vision only)
    try:
        client = get_client()
        models = await client.list()
        model_names = [m["model"] for m in models.get("models", [])]
        result["ollama"] = {
            "status": "connected",
            "models": model_names,
            "inference_model_available": INFERENCE_MODEL in model_names,
        }
    except Exception as e:
        logger.error(f"Ollama health check failed: {e}")
        result["ollama"] = {"status": "disconnected", "error": str(e)}

    # OpenAI — used for embeddings (primary) + chat/vision fallback
    result["openai"] = {
        "configured": bool(OPENAI_API_KEY),
        "embedding_model": OPENAI_EMBEDDING_MODEL,
        "inference_model": OPENAI_INFERENCE_MODEL,
    }
    return result
