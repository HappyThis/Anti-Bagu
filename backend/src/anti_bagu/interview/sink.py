from __future__ import annotations

from typing import Protocol

from anti_bagu.interview.events import RealtimeEvent


class EventSink(Protocol):
    async def publish(self, event: RealtimeEvent) -> None: ...


class MemoryEventSink:
    def __init__(self) -> None:
        self.events: list[RealtimeEvent] = []

    async def publish(self, event: RealtimeEvent) -> None:
        self.events.append(event)
