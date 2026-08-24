from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from anti_bagu.interview.events import (
    Channel,
    CommittedFocus,
    ConversationTurn,
    FocusSource,
)
from anti_bagu.persistence.models import TaskEvent

RUNTIME_EVENT_TYPES = (
    "transcript.committed",
    "focus.updated",
    "answer.completed",
    "focus.wait",
    "focus.unchanged",
)


@dataclass(frozen=True, slots=True)
class PersistedRuntimeState:
    turns: tuple[ConversationTurn, ...]
    focuses: tuple[CommittedFocus, ...]
    last_analyzed_turn_id: int


async def load_runtime_state(
    sessions: async_sessionmaker[AsyncSession], task_id: str
) -> PersistedRuntimeState:
    async with sessions() as session:
        rows = (
            await session.scalars(
                select(TaskEvent)
                .where(TaskEvent.task_id == task_id)
                .where(TaskEvent.event_type.in_(RUNTIME_EVENT_TYPES))
                .order_by(TaskEvent.created_at.asc(), TaskEvent.id.asc())
            )
        ).all()

    turns: list[ConversationTurn] = []
    focus_order: list[str] = []
    focus_values: dict[str, dict[str, object]] = {}
    last_analyzed_turn_id = 0
    for row in rows:
        payload = row.payload
        if row.event_type == "transcript.committed":
            turn_id = int(payload.get("turn_id") or 0)
            text = str(payload.get("text") or "").strip()
            if turn_id and text:
                turns.append(
                    ConversationTurn(
                        turn_id=turn_id,
                        channel=Channel(str(payload.get("channel") or "candidate")),
                        text=text,
                        event_id=str(payload.get("source_event_id") or row.event_id),
                        created_at=row.created_at.timestamp(),
                    )
                )
            continue

        if row.event_type in {"focus.wait", "focus.unchanged"}:
            last_analyzed_turn_id = max(
                last_analyzed_turn_id, int(payload.get("through_turn_id") or 0)
            )
            continue

        focus_id = str(payload.get("focus_id") or "")
        if not focus_id:
            continue
        value = focus_values.get(focus_id)
        if value is None:
            value = {
                "focus_id": focus_id,
                "question": "",
                "recommended_answer": "",
                "code": None,
                "source": FocusSource.VOICE,
                "screenshot_id": "",
                "source_start_turn_id": 0,
                "source_end_turn_id": 0,
                "created_at": row.created_at.timestamp(),
            }
            focus_values[focus_id] = value
            focus_order.append(focus_id)
        value["question"] = str(payload.get("question") or value["question"])
        value["source"] = _focus_source(payload.get("source"))
        value["screenshot_id"] = str(
            payload.get("screenshot_id") or value["screenshot_id"]
        )
        if row.event_type == "focus.updated":
            value["source_start_turn_id"] = int(
                payload.get("source_start_turn_id") or value["source_start_turn_id"]
            )
            value["source_end_turn_id"] = int(
                payload.get("source_end_turn_id") or value["source_end_turn_id"]
            )
            last_analyzed_turn_id = max(
                last_analyzed_turn_id, int(value["source_end_turn_id"])
            )
        elif row.event_type == "answer.completed":
            value["recommended_answer"] = str(payload.get("answer") or "")
            value["code"] = str(payload.get("code") or "").strip() or None

    turns.sort(key=lambda turn: turn.turn_id)
    focuses = tuple(
        CommittedFocus.model_validate(focus_values[focus_id])
        for focus_id in focus_order
        if str(focus_values[focus_id]["question"]).strip()
    )
    return PersistedRuntimeState(
        turns=tuple(turns),
        focuses=focuses,
        last_analyzed_turn_id=last_analyzed_turn_id,
    )


def _focus_source(value: object) -> FocusSource:
    try:
        return FocusSource(str(value or FocusSource.VOICE.value))
    except ValueError:
        return FocusSource.VOICE
