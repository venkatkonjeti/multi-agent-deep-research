"""
Knowledge Agent — Queries the LLM directly for its parametric knowledge.
Assesses confidence of the response to decide if web search is needed.
"""
from __future__ import annotations

import logging

from ..core.event_bus import EventBus
from ..core.llm_client import chat

from ..config import LOW_CONFIDENCE_INDICATORS, INFERENCE_MODEL

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You are a knowledgeable research assistant. Answer the user's question thoroughly and accurately based on your training knowledge.

Important rules:
- If you are confident in your answer, provide a detailed response.
- If you are NOT confident, unsure, or your knowledge is outdated/insufficient, clearly state so. Use phrases like "I'm not sure", "I don't have enough information", or "my knowledge may be outdated".
- Do NOT fabricate facts. If unsure, say so.
- Include relevant details, data, and context when available.
- Format your response with markdown when appropriate."""


def _assess_confidence(response: str) -> dict:
    """
    Analyze the model's response for low-confidence indicators.
    Returns {confident: bool, indicators_found: [str]}.
    """
    response_lower = response.lower()
    found = [
        indicator
        for indicator in LOW_CONFIDENCE_INDICATORS
        if indicator in response_lower
    ]
    # Also check if response is very short (likely insufficient)
    too_short = len(response.strip()) < 100

    return {
        "confident": len(found) == 0 and not too_short,
        "indicators_found": found,
        "too_short": too_short,
    }


async def run(
    query: str,
    event_bus: EventBus,
    conversation_history: list[dict] | None = None,
) -> dict:
    """
    Query the LLM directly and assess confidence.

    Returns:
        {
            "response": str,
            "confident": bool,
            "confidence_detail": dict,
        }
    """
    await event_bus.agent_start(
        "knowledge", f"Querying {INFERENCE_MODEL} for knowledge..."
    )

    try:
        messages = [{"role": "system", "content": _SYSTEM_PROMPT}]

        # Include conversation history for context
        if conversation_history:
            messages.extend(conversation_history[-6:])  # last 3 turns

        messages.append({"role": "user", "content": query})

        response = await chat(messages=messages, temperature=0.4)
        confidence = _assess_confidence(response)

        if confidence["confident"]:
            await event_bus.agent_result(
                "knowledge",
                "Model provided a confident response",
                confident=True,
                response_length=len(response),
            )
        else:
            reasons = []
            if confidence["indicators_found"]:
                reasons.append(
                    f"low-confidence phrases: {confidence['indicators_found'][:3]}"
                )
            if confidence["too_short"]:
                reasons.append("response too short")
            await event_bus.agent_result(
                "knowledge",
                f"Model response has low confidence ({', '.join(reasons)})",
                confident=False,
            )

        return {
            "response": response,
            "confident": confidence["confident"],
            "confidence_detail": confidence,
        }

    except Exception as e:
        logger.error(f"Knowledge agent error: {e}")
        await event_bus.agent_error("knowledge", f"Error: {e}")
        return {
            "response": "",
            "confident": False,
            "confidence_detail": {"error": str(e)},
        }
