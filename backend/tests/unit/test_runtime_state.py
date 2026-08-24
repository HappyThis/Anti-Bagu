from __future__ import annotations

from anti_bagu.persistence.database import create_database, create_schema
from anti_bagu.persistence.models import TaskEvent
from anti_bagu.persistence.runtime_state import load_runtime_state


async def test_runtime_state_restores_turns_focus_code_and_analysis_watermark(
    tmp_path,
) -> None:
    engine, sessions = create_database(
        f"sqlite+aiosqlite:///{tmp_path / 'runtime-state.db'}"
    )
    await create_schema(engine)
    async with sessions() as session:
        session.add_all(
            [
                TaskEvent(
                    task_id="task-1",
                    event_id="turn-1",
                    event_type="transcript.committed",
                    conversation_revision=1,
                    payload={
                        "turn_id": 1,
                        "channel": "interviewer",
                        "text": "怎么反转链表？",
                        "source_event_id": "source-1",
                    },
                ),
                TaskEvent(
                    task_id="task-1",
                    event_id="focus-1",
                    event_type="focus.updated",
                    conversation_revision=1,
                    payload={
                        "focus_id": "current-focus",
                        "question": "反转链表",
                        "source": "VOICE",
                        "source_start_turn_id": 1,
                        "source_end_turn_id": 1,
                    },
                ),
                TaskEvent(
                    task_id="task-1",
                    event_id="answer-1",
                    event_type="answer.completed",
                    conversation_revision=1,
                    payload={
                        "focus_id": "current-focus",
                        "question": "反转链表",
                        "answer": "使用三个指针。",
                        "code": "def reverse(head):\n    return head",
                        "source": "VOICE",
                    },
                ),
                TaskEvent(
                    task_id="task-1",
                    event_id="turn-2",
                    event_type="transcript.committed",
                    conversation_revision=1,
                    payload={
                        "turn_id": 2,
                        "channel": "candidate",
                        "text": "我理解了。",
                        "source_event_id": "source-2",
                    },
                ),
                TaskEvent(
                    task_id="task-1",
                    event_id="wait-2",
                    event_type="focus.wait",
                    conversation_revision=1,
                    payload={"through_turn_id": 2},
                ),
            ]
        )
        await session.commit()

    state = await load_runtime_state(sessions, "task-1")
    await engine.dispose()

    assert [turn.text for turn in state.turns] == ["怎么反转链表？", "我理解了。"]
    assert state.focuses[0].focus_id == "current-focus"
    assert state.focuses[0].recommended_answer == "使用三个指针。"
    assert state.focuses[0].code == "def reverse(head):\n    return head"
    assert state.last_analyzed_turn_id == 2
