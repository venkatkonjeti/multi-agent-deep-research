"""
Event Bus — Real-time agent trace event system.
Agents emit status events; the FastAPI SSE endpoint streams them to the React frontend.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class EventType(str, Enum):
    """Types of agent trace events."""
    AGENT_START = "agent_start"
    AGENT_PROGRESS = "agent_progress"
    AGENT_RESULT = "agent_result"
    AGENT_ERROR = "agent_error"
    STREAM_TOKEN = "stream_token"
    STREAM_END = "stream_end"
    PLAN_STEP = "plan_step"


@dataclass
class AgentEvent:
    """A single agent trace event."""
    event_type: EventType
    agent_name: str
    message: str
    data: dict = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def to_sse(self) -> str:
        """Format as SSE data line."""
        payload = {
            "type": self.event_type.value,
            "agent": self.agent_name,
            "message": self.message,
            "data": self.data,
            "timestamp": self.timestamp,
        }
        return f"data: {json.dumps(payload)}\n\n"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["event_type"] = self.event_type.value
        return d


class EventBus:
    """
    Per-request event bus. Each user query gets its own EventBus instance.
    Agents push events; the SSE endpoint consumes them.
    """

    def __init__(self):
        self._queue: asyncio.Queue[AgentEvent | None] = asyncio.Queue()
        self._trace: list[AgentEvent] = []
        self._closed = False

    def emit(self, event: AgentEvent) -> None:
        """Push an event (non-async, safe to call from sync context too)."""
        if self._closed:
            return
        self._trace.append(event)
        try:
            self._queue.put_nowait(event)
        except asyncio.QueueFull:
            logger.warning("Event queue full, dropping event")

    async def emit_async(self, event: AgentEvent) -> None:
        """Push an event (async)."""
        if self._closed:
            return
        self._trace.append(event)
        await self._queue.put(event)

    # ─── Convenience emitters ────────────────────────────────

    async def agent_start(self, agent: str, message: str, **data):
        await self.emit_async(AgentEvent(
            event_type=EventType.AGENT_START,
            agent_name=agent,
            message=message,
            data=data,
        ))

    async def agent_progress(self, agent: str, message: str, **data):
        await self.emit_async(AgentEvent(
            event_type=EventType.AGENT_PROGRESS,
            agent_name=agent,
            message=message,
            data=data,
        ))

    async def agent_result(self, agent: str, message: str, **data):
        await self.emit_async(AgentEvent(
            event_type=EventType.AGENT_RESULT,
            agent_name=agent,
            message=message,
            data=data,
        ))

    async def agent_error(self, agent: str, message: str, **data):
        await self.emit_async(AgentEvent(
            event_type=EventType.AGENT_ERROR,
            agent_name=agent,
            message=message,
            data=data,
        ))

    async def plan_step(self, message: str, **data):
        await self.emit_async(AgentEvent(
            event_type=EventType.PLAN_STEP,
            agent_name="orchestrator",
            message=message,
            data=data,
        ))

    async def stream_token(self, token: str):
        await self.emit_async(AgentEvent(
            event_type=EventType.STREAM_TOKEN,
            agent_name="synthesis",
            message=token,
        ))

    async def stream_end(self):
        await self.emit_async(AgentEvent(
            event_type=EventType.STREAM_END,
            agent_name="synthesis",
            message="",
        ))

    # ─── Consumption ─────────────────────────────────────────

    async def subscribe(self):
        """Async generator that yields events until the bus is closed."""
        while True:
            event = await self._queue.get()
            if event is None:  # sentinel
                break
            yield event

    def close(self) -> None:
        """Signal that no more events will be emitted."""
        self._closed = True
        try:
            self._queue.put_nowait(None)  # sentinel to unblock subscriber
        except asyncio.QueueFull:
            pass

    def get_trace(self) -> list[dict]:
        """Return full trace for persistence."""
        return [e.to_dict() for e in self._trace]
