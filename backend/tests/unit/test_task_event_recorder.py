from __future__ import annotations

from sqlalchemy import select

from anti_bagu.interview.events import RealtimeEvent
from anti_bagu.persistence.database import create_database, create_schema
from anti_bagu.persistence.models import TaskEvent
from anti_bagu.persistence.task_events import TaskEventRecorder


def event(event_type: str, event_id: str) -> RealtimeEvent:
    return RealtimeEvent(
        type=event_type,
        event_id=event_id,
        session_id="task-1",
        conversation_revision=1,
        payload={"text": "测试"} if event_type.startswith("transcript.") else {},
    )


async def test_recorder_persists_only_durable_event_whitelist(tmp_path) -> None:
    engine, sessions = create_database(
        f"sqlite+aiosqlite:///{tmp_path / 'events.db'}"
    )
    await create_schema(engine)
    recorder = TaskEventRecorder("task-1", sessions)
    await recorder.start()

    await recorder.record(event("transcript.partial", "partial"))
    await recorder.record(event("transcript.final", "final"))
    await recorder.record(event("audio.connected", "audio"))
    await recorder.record(event("latency.updated", "latency"))
    await recorder.record(event("focus.window.started", "window"))
    await recorder.record(event("task.status", "status"))
    await recorder.record(event("transcript.committed", "committed"))
    await recorder.record(event("answer.completed", "answer"))
    await recorder.record(event("internal.llm.request", "llm-request"))
    await recorder.record(event("task.metrics", "metrics"))
    await recorder.close()

    async with sessions() as session:
        rows = (
            await session.scalars(select(TaskEvent).order_by(TaskEvent.id.asc()))
        ).all()
    await engine.dispose()

    assert [row.event_type for row in rows] == [
        "transcript.committed",
        "answer.completed",
        "internal.llm.request",
        "task.metrics",
    ]


async def test_recorder_retries_transient_database_failure(tmp_path) -> None:
    engine, sessions = create_database(
        f"sqlite+aiosqlite:///{tmp_path / 'retry.db'}"
    )
    await create_schema(engine)
    recorder = TaskEventRecorder(
        "task-1",
        sessions,
        write_attempts=3,
        retry_delay_seconds=0,
    )
    original_persist = recorder._persist_once
    attempts = 0

    async def flaky_persist(events):
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise ConnectionError("temporary database outage")
        await original_persist(events)

    recorder._persist_once = flaky_persist
    await recorder.start()
    await recorder.record(event("transcript.committed", "committed"))
    await recorder.close()

    async with sessions() as session:
        rows = (await session.scalars(select(TaskEvent))).all()
    await engine.dispose()

    assert attempts == 3
    assert recorder.dropped == 0
    assert [row.event_id for row in rows] == ["committed"]


async def test_recorder_treats_post_commit_disconnect_as_success(tmp_path) -> None:
    engine, sessions = create_database(
        f"sqlite+aiosqlite:///{tmp_path / 'post-commit.db'}"
    )
    await create_schema(engine)
    recorder = TaskEventRecorder(
        "task-1",
        sessions,
        write_attempts=3,
        retry_delay_seconds=0,
    )
    original_persist = recorder._persist_once
    attempts = 0

    async def disconnected_after_commit(events):
        nonlocal attempts
        attempts += 1
        await original_persist(events)
        raise ConnectionError("connection closed after commit")

    recorder._persist_once = disconnected_after_commit
    await recorder.start()
    await recorder.record(event("answer.completed", "answer"))
    await recorder.close()

    async with sessions() as session:
        rows = (await session.scalars(select(TaskEvent))).all()
    await engine.dispose()

    assert attempts == 1
    assert recorder.dropped == 0
    assert [row.event_id for row in rows] == ["answer"]
