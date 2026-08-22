from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from anti_bagu.interview.events import RealtimeEvent
from anti_bagu.persistence.models import TaskEvent

SKIPPED_EVENTS = {"audio.level"}
LOGGER = logging.getLogger(__name__)


class TaskEventRecorder:
    """Persist important task events to PostgreSQL and per-task JSONL files."""

    def __init__(
        self,
        task_id: str,
        session_factory: async_sessionmaker[AsyncSession],
        storage_dir: Path,
        *,
        queue_size: int = 4_096,
    ) -> None:
        self.task_id = task_id
        self._sessions = session_factory
        self._directory = storage_dir / "tasks" / task_id / "events"
        self._queue: asyncio.Queue[RealtimeEvent | None] = asyncio.Queue(
            maxsize=queue_size
        )
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
        if event.type in SKIPPED_EVENTS:
            return
        try:
            self._queue.put_nowait(event)
        except asyncio.QueueFull:
            self.dropped += 1

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
                await self._persist(batch)
            except Exception:
                self.dropped += len(batch)
                LOGGER.exception("Unable to persist task events for %s", self.task_id)
            if stop:
                return

    async def _persist(self, events: list[RealtimeEvent]) -> None:
        await asyncio.to_thread(self._append_jsonl, events)
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

    def _append_jsonl(self, events: list[RealtimeEvent]) -> None:
        self._directory.mkdir(parents=True, exist_ok=True)
        by_day: dict[str, list[str]] = {}
        for event in events:
            day = datetime.fromtimestamp(event.created_at, UTC).date().isoformat()
            by_day.setdefault(day, []).append(
                json.dumps(event.model_dump(mode="json"), ensure_ascii=False)
            )
        for day, lines in by_day.items():
            with (self._directory / f"{day}.jsonl").open(
                "a", encoding="utf-8"
            ) as handle:
                handle.write("\n".join(lines) + "\n")
