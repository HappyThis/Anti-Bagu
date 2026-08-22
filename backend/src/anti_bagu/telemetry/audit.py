from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import time
from collections import deque
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from typing import Any

from anti_bagu.interview.events import RealtimeEvent

_TEXT_FIELDS = {"answer", "delta", "prompt", "question", "text"}
_SECRET_FIELDS = {
    "api_key",
    "authorization",
    "secret",
    "token",
    "access_token",
    "refresh_token",
}
_SECRET_PATTERNS = (
    re.compile(r"(?i)bearer\s+[a-z0-9._-]+"),
    re.compile(r"\bsk-[a-zA-Z0-9._-]{12,}\b"),
)
_SKIPPED_REALTIME_EVENTS = {"audio.level"}
_LATENCY_KEYS = {"asr", "endToEnd", "model"}
LOGGER = logging.getLogger(__name__)


class DailyJsonlAudit:
    """Non-blocking local audit trail with one JSONL file per local calendar day."""

    def __init__(
        self,
        directory: Path,
        *,
        session_id: str,
        include_text: bool = False,
        ring_size: int = 1_000,
        queue_size: int = 4_096,
    ) -> None:
        self.directory = directory
        self.session_id = session_id
        self.include_text = include_text
        self._recent: deque[dict[str, Any]] = deque(maxlen=max(1, ring_size))
        self._queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue(
            maxsize=max(1, queue_size)
        )
        self._writer_task: asyncio.Task[None] | None = None
        self._dropped = 0

    @property
    def dropped(self) -> int:
        return self._dropped

    async def start(self) -> None:
        if self._writer_task is None or self._writer_task.done():
            self._writer_task = asyncio.create_task(
                self._writer_loop(), name="anti-bagu-audit-writer"
            )

    async def close(self) -> None:
        writer = self._writer_task
        if writer is None:
            return
        if writer.done():
            await asyncio.gather(writer, return_exceptions=True)
            self._writer_task = None
            return
        await self._queue.put(None)
        await writer
        self._writer_task = None

    def record_realtime(self, event: RealtimeEvent) -> None:
        if event.type in _SKIPPED_REALTIME_EVENTS:
            return
        if event.type == "latency.updated" and not (
            _LATENCY_KEYS & event.payload.keys()
        ):
            return
        self.emit(
            event.type,
            payload=event.payload,
            session_id=event.session_id,
            conversation_revision=event.conversation_revision,
            created_at=event.created_at,
            event_id=event.event_id,
        )

    def emit(
        self,
        event: str,
        *,
        payload: dict[str, Any] | None = None,
        level: str = "INFO",
        session_id: str | None = None,
        conversation_revision: int | None = None,
        created_at: float | None = None,
        event_id: str | None = None,
    ) -> None:
        timestamp = created_at if created_at is not None else time.time()
        local_time = datetime.fromtimestamp(timestamp).astimezone()
        record: dict[str, Any] = {
            "timestamp": local_time.isoformat(timespec="milliseconds"),
            "created_at": timestamp,
            "level": level,
            "event": event,
            "session_id": session_id or self.session_id,
            "payload": self._redact(payload or {}),
        }
        if conversation_revision is not None:
            record["conversation_revision"] = conversation_revision
        if event_id is not None:
            record["event_id"] = event_id
        self._recent.append(record)
        try:
            self._queue.put_nowait(record)
        except asyncio.QueueFull:
            self._dropped += 1

    def recent(
        self,
        *,
        limit: int = 200,
        event_prefix: str | None = None,
    ) -> list[dict[str, Any]]:
        if limit <= 0:
            return []
        selected: Iterable[dict[str, Any]] = self._recent
        if event_prefix:
            selected = (
                item
                for item in selected
                if str(item.get("event", "")).startswith(event_prefix)
            )
        return list(selected)[-min(limit, self._recent.maxlen or limit) :]

    async def _writer_loop(self) -> None:
        while True:
            first = await self._queue.get()
            if first is None:
                return
            batch = [first]
            should_stop = False
            while len(batch) < 200:
                try:
                    item = self._queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
                if item is None:
                    should_stop = True
                    break
                batch.append(item)
            try:
                await asyncio.to_thread(self._write_batch, batch)
            except Exception:
                self._dropped += len(batch)
                LOGGER.exception("Unable to persist Anti-Bagu audit events")
            if should_stop:
                return

    def _write_batch(self, records: list[dict[str, Any]]) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        by_day: dict[str, list[str]] = {}
        for record in records:
            timestamp = float(record["created_at"])
            day = datetime.fromtimestamp(timestamp).astimezone().date().isoformat()
            by_day.setdefault(day, []).append(
                json.dumps(record, ensure_ascii=False, separators=(",", ":"))
            )
        for day, lines in by_day.items():
            path = self.directory / f"{day}.jsonl"
            with path.open("a", encoding="utf-8") as handle:
                handle.write("\n".join(lines))
                handle.write("\n")

    def _redact(self, value: Any, *, field: str | None = None) -> Any:
        normalized_field = field.lower() if field else None
        if normalized_field in _SECRET_FIELDS:
            return "[REDACTED]"
        if normalized_field in _TEXT_FIELDS and not self.include_text:
            text = str(value)
            return {
                "redacted": True,
                "characters": len(text),
                "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()[:12],
            }
        if isinstance(value, dict):
            return {
                str(key): self._redact(item, field=str(key))
                for key, item in value.items()
            }
        if isinstance(value, (list, tuple)):
            return [self._redact(item) for item in value]
        if isinstance(value, str):
            sanitized = value
            for pattern in _SECRET_PATTERNS:
                sanitized = pattern.sub("[REDACTED]", sanitized)
            return sanitized
        return value
