from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest

from anti_bagu.telemetry.audit import DailyJsonlAudit


@pytest.mark.asyncio
async def test_audit_writes_one_jsonl_file_per_local_day(tmp_path) -> None:
    audit = DailyJsonlAudit(tmp_path, session_id="session", include_text=True)
    local_tz = datetime.now().astimezone().tzinfo
    first_day = datetime(2026, 8, 20, 23, 59, tzinfo=local_tz)
    second_day = first_day + timedelta(minutes=2)

    await audit.start()
    audit.emit("focus.started", created_at=first_day.timestamp())
    audit.emit("focus.responded", created_at=second_day.timestamp())
    await audit.close()

    first_records = [
        json.loads(line)
        for line in (tmp_path / "2026-08-20.jsonl").read_text().splitlines()
    ]
    second_records = [
        json.loads(line)
        for line in (tmp_path / "2026-08-21.jsonl").read_text().splitlines()
    ]
    assert [item["event"] for item in first_records] == ["focus.started"]
    assert [item["event"] for item in second_records] == ["focus.responded"]


@pytest.mark.asyncio
async def test_audit_redacts_text_and_secrets_by_default(tmp_path) -> None:
    audit = DailyJsonlAudit(tmp_path, session_id="session")
    await audit.start()
    audit.emit(
        "transcript.final",
        payload={
            "text": "Redis 为什么快？",
            "api_key": "not-a-real-key",
            "message": "authorization Bearer sk-example123456789",
        },
    )
    await audit.close()

    record = audit.recent(limit=1)[0]
    assert record["payload"]["text"]["redacted"] is True
    assert record["payload"]["text"]["characters"] == len("Redis 为什么快？")
    assert record["payload"]["api_key"] == "[REDACTED]"
    assert "sk-example" not in record["payload"]["message"]


def test_audit_recent_can_filter_by_event_prefix(tmp_path) -> None:
    audit = DailyJsonlAudit(tmp_path, session_id="session")
    audit.emit("focus.started")
    audit.emit("transcript.final")
    audit.emit("focus.wait")

    assert [item["event"] for item in audit.recent(event_prefix="focus.")] == [
        "focus.started",
        "focus.wait",
    ]
