from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from anti_bagu.interview.events import RealtimeEvent
from anti_bagu.persistence.models import TaskEvent

PERSISTED_EVENT_TYPES = frozenset(
    {
        "transcript.committed",
        "focus.updated",
        "answer.completed",
        "focus.wait",
        "focus.unchanged",
        "focus.blocked",
        "focus.cancelled",
        "focus.discarded",
        "focus.abandoned",
        "focus.timeout",
        "focus.error",
        "focus.retry_succeeded",
        "internal.llm.request",
        "internal.llm.response",
        "internal.llm.output_invalid",
        "screenshot.accepted",
        "screenshot.rejected",
        "screenshot.focus.released",
        "preflight.completed",
        "task.metrics",
        "error",
    }
)
LOGGER = logging.getLogger(__name__)


class TaskEventRecorder:
    """Persist the durable task event stream to PostgreSQL."""

    def __init__(
        self,
        task_id: str,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        queue_size: int = 4_096,
        write_attempts: int = 3,
        retry_delay_seconds: float = 0.1,
    ) -> None:
        self.task_id = task_id
        self._sessions = session_factory
        self._queue: asyncio.Queue[RealtimeEvent | None] = asyncio.Queue(
            maxsize=queue_size
        )
        self._write_attempts = max(1, write_attempts)
        self._retry_delay_seconds = max(0.0, retry_delay_seconds)
        self._writer: asyncio.Task[None] | None = None
        self.dropped = 0

    async def start(self) -> None:
        if self._writer is None or self._writer.done():
            self._writer = asyncio.create_task(
                self._writer_loop(), name=f"task-events-{self.task_id}"
            )

    async def close(self) -> None:
        if self._writer is None:
            return
        await self._queue.put(None)
        await self._writer
        self._writer = None

    async def record(self, event: RealtimeEvent) -> None:
        if event.type not in PERSISTED_EVENT_TYPES:
            return
        # Durable events are deliberately low-volume. Backpressure is safer than
        # silently dropping a transcript, focus watermark, or model result.
        await self._queue.put(event)

    async def _writer_loop(self) -> None:
        while True:
            first = await self._queue.get()
            if first is None:
                return
            batch = [first]
            stop = False
            while len(batch) < 100:
                try:
                    event = self._queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
                if event is None:
                    stop = True
                    break
                batch.append(event)
            try:
                await self._persist_with_retry(batch)
            except Exception:
                self.dropped += len(batch)
                LOGGER.exception("Unable to persist task events for %s", self.task_id)
            if stop:
                return

    async def _persist_with_retry(self, events: list[RealtimeEvent]) -> None:
        for attempt in range(1, self._write_attempts + 1):
            try:
                await self._persist_once(events)
                return
            except Exception:
                try:
                    if await self._batch_already_persisted(events):
                        return
                except Exception:
                    pass
                if attempt >= self._write_attempts:
                    raise
                LOGGER.warning(
                    "Task event write failed for %s; retrying (%s/%s)",
                    self.task_id,
                    attempt,
                    self._write_attempts,
                    exc_info=True,
                )
                await asyncio.sleep(self._retry_delay_seconds * (2 ** (attempt - 1)))

    async def _persist_once(self, events: list[RealtimeEvent]) -> None:
        rows = [
            TaskEvent(
                task_id=self.task_id,
                event_id=event.event_id,
                event_type=event.type,
                conversation_revision=event.conversation_revision,
                payload=event.payload,
                created_at=datetime.fromtimestamp(event.created_at, UTC),
            )
            for event in events
        ]
        async with self._sessions() as session:
            session.add_all(rows)
            await session.commit()

    async def _batch_already_persisted(
        self, events: list[RealtimeEvent]
    ) -> bool:
        expected = {event.event_id for event in events}
        async with self._sessions() as session:
            stored = set(
                await session.scalars(
                    select(TaskEvent.event_id).where(
                        TaskEvent.event_id.in_(expected)
                    )
                )
            )
        return stored == expected
