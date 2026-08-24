from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from anti_bagu.interview.events import RealtimeEvent
from anti_bagu.telemetry.audit import DailyJsonlAudit

_SUMMARY_LATENCY_KEYS = ("asr", "model", "endToEnd")


class EventHub:
    def __init__(
        self,
        queue_size: int = 256,
        *,
        audit: DailyJsonlAudit | None = None,
        recorder: Callable[[RealtimeEvent], Awaitable[None]] | None = None,
    ) -> None:
        self._queue_size = queue_size
        self._audit = audit
        self._recorder = recorder
        self._subscribers: set[asyncio.Queue[RealtimeEvent]] = set()
        self._audio_status: dict[str, RealtimeEvent] = {}
        self._latency_event: RealtimeEvent | None = None
        self._latency_totals = {key: 0.0 for key in _SUMMARY_LATENCY_KEYS}
        self._latency_counts = {key: 0 for key in _SUMMARY_LATENCY_KEYS}
        self._screenshot_event: RealtimeEvent | None = None

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)

    def latency_summary(self) -> dict[str, float | int]:
        payload: dict[str, float | int] = {}
        names = {
            "asr": "asr",
            "model": "model",
            "endToEnd": "end_to_end",
        }
        for key, name in names.items():
            count = self._latency_counts[key]
            payload[f"{name}_sample_count"] = count
            payload[f"{name}_avg_ms"] = (
                round(self._latency_totals[key] / count, 2) if count else 0.0
            )
        return payload

    async def publish(self, event: RealtimeEvent) -> None:
        if self._audit is not None:
            self._audit.record_realtime(event)
        if self._recorder is not None:
            await self._recorder(event)
        if event.type in {"audio.connected", "audio.disconnected"}:
            channel = str(event.payload.get("channel", ""))
            if channel:
                self._audio_status[channel] = event
        elif event.type == "latency.updated":
            for key in _SUMMARY_LATENCY_KEYS:
                value = event.payload.get(key)
                if (
                    isinstance(value, (int, float))
                    and not isinstance(value, bool)
                    and value >= 0
                ):
                    self._latency_totals[key] += float(value)
                    self._latency_counts[key] += 1
            merged_payload = (
                dict(self._latency_event.payload)
                if self._latency_event is not None
                else {}
            )
            merged_payload.update(event.payload)
            self._latency_event = event.model_copy(
                update={"payload": merged_payload}
            )
        elif event.type in {"screenshot.accepted", "screenshot.focus.released"}:
            self._screenshot_event = event
        if event.type.startswith("internal."):
            return
        for queue in tuple(self._subscribers):
            if queue.full():
                queue.get_nowait()
            queue.put_nowait(event)

    @asynccontextmanager
    async def subscribe(self) -> AsyncIterator[asyncio.Queue[RealtimeEvent]]:
        queue: asyncio.Queue[RealtimeEvent] = asyncio.Queue(maxsize=self._queue_size)
        self._subscribers.add(queue)
        for event in self._audio_status.values():
            queue.put_nowait(event)
        if self._latency_event is not None:
            queue.put_nowait(self._latency_event)
        if self._screenshot_event is not None:
            queue.put_nowait(self._screenshot_event)
        try:
            yield queue
        finally:
            self._subscribers.discard(queue)
