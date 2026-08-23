from __future__ import annotations

import asyncio

import pytest
from fakes.models import (
    BlockingFocusResponder,
    BlockingScreenshotAnalyzer,
    FakeFocusResponder,
    FakeScreenshotAnalyzer,
    PreemptibleFocusResponder,
    SequencedFocusResponder,
)

from anti_bagu.interview.context import FocusPromptBuilder
from anti_bagu.interview.coordinator import InterviewCoordinator
from anti_bagu.interview.events import (
    AnswerResult,
    Channel,
    FocusSource,
    TranscriptEvent,
    TranscriptPhase,
    WaitResult,
)
from anti_bagu.interview.sink import MemoryEventSink


def transcript(
    channel: Channel,
    phase: TranscriptPhase,
    text: str,
    *,
    utterance_id: str = "utterance-1",
) -> TranscriptEvent:
    return TranscriptEvent(
        channel=channel,
        phase=phase,
        text=text,
        utterance_id=utterance_id,
    )


def coordinator(
    responder,
    *,
    screenshot=None,
    sink=None,
    debounce_seconds: float = 0,
) -> InterviewCoordinator:
    return InterviewCoordinator(
        responder,
        screenshot or FakeScreenshotAnalyzer(wait_result()),
        sink or MemoryEventSink(),
        FocusPromptBuilder(system_prompt="I 是面试官，C 是候选人。返回 JSON。"),
        debounce_seconds=debounce_seconds,
        max_coalesce_seconds=max(debounce_seconds * 4, 0.01),
    )


def wait_result() -> WaitResult:
    return WaitResult(type="wait")


def answer_result(
    question: str,
    answer: str = "简短回答。",
    code: str | None = None,
) -> AnswerResult:
    return AnswerResult(
        type="answer",
        question=question,
        answer=answer,
        code=code,
    )


@pytest.mark.asyncio
async def test_candidate_final_is_stored_without_triggering_focus() -> None:
    responder = FakeFocusResponder(wait_result())
    subject = coordinator(responder)

    await subject.handle_transcript(
        transcript(Channel.CANDIDATE, TranscriptPhase.FINAL, "我先说一下自己的理解")
    )
    await subject.wait_idle()

    assert responder.calls == []
    assert subject.store.revision == 0
    assert [(turn.turn_id, turn.text) for turn in subject.store.turns] == [
        (1, "我先说一下自己的理解")
    ]


@pytest.mark.asyncio
async def test_interviewer_final_commits_focus_and_recommendation() -> None:
    responder = FakeFocusResponder(
        answer_result("Redis 为什么快？", "因为内存和 I/O 多路复用。")
    )
    sink = MemoryEventSink()
    subject = coordinator(responder, sink=sink)

    await subject.handle_transcript(
        transcript(Channel.INTERVIEWER, TranscriptPhase.FINAL, "Redis 为什么快？")
    )
    await subject.wait_idle()

    assert len(responder.calls) == 1
    assert "- I（最新）: Redis 为什么快？" in responder.calls[0]["prompt"]
    assert subject.store.current_focus == "Redis 为什么快？"
    assert subject.store.current_recommended_answer == "因为内存和 I/O 多路复用。"
    assert [event.type for event in sink.events].count("answer.completed") == 1
    lifecycle = [event.type for event in sink.events]
    assert "transcript.committed" in lifecycle
    assert "focus.window.started" in lifecycle
    assert "focus.window.fired" in lifecycle
    assert "focus.started" in lifecycle
    assert "focus.responded" in lifecycle


@pytest.mark.asyncio
async def test_two_quick_finals_share_one_debounced_request() -> None:
    responder = FakeFocusResponder(answer_result("MySQL 中如何定位慢查询？"))
    subject = coordinator(responder, debounce_seconds=0.03)

    await subject.handle_transcript(
        transcript(Channel.INTERVIEWER, TranscriptPhase.FINAL, "在 MySQL 中。")
    )
    await asyncio.sleep(0.01)
    await subject.handle_transcript(
        transcript(
            Channel.INTERVIEWER,
            TranscriptPhase.FINAL,
            "如何定位慢查询？",
            utterance_id="utterance-2",
        )
    )
    await subject.wait_idle()

    assert len(responder.calls) == 1
    assert "在 MySQL 中。如何定位慢查询？" in responder.calls[0]["prompt"]
    assert len(subject.store.turns) == 2


@pytest.mark.asyncio
async def test_candidate_final_does_not_cancel_active_focus() -> None:
    responder = BlockingFocusResponder(answer_result("什么是 AQS？"))
    subject = coordinator(responder)

    await subject.handle_transcript(
        transcript(Channel.INTERVIEWER, TranscriptPhase.FINAL, "什么是 AQS？")
    )
    await responder.started.wait()
    await subject.handle_transcript(
        transcript(
            Channel.CANDIDATE,
            TranscriptPhase.FINAL,
            "我知道它和锁有关",
            utterance_id="candidate-1",
        )
    )

    assert subject.model_task_active
    assert not responder.cancelled
    responder.release.set()
    await subject.wait_idle()
    assert subject.store.current_focus == "什么是 AQS？"
    assert len(subject.store.turns) == 2


@pytest.mark.asyncio
async def test_interviewer_partial_does_not_cancel_running_focus() -> None:
    responder = BlockingFocusResponder(answer_result("什么是 AQS？"))
    subject = coordinator(responder)

    await subject.handle_transcript(
        transcript(Channel.INTERVIEWER, TranscriptPhase.FINAL, "什么是 AQS？")
    )
    await responder.started.wait()
    await subject.handle_transcript(
        transcript(
            Channel.INTERVIEWER,
            TranscriptPhase.PARTIAL,
            "还有一个约束",
            utterance_id="interviewer-2",
        )
    )

    assert not responder.cancelled
    responder.release.set()
    await subject.wait_idle()


@pytest.mark.asyncio
async def test_new_focus_attempt_preempts_old_attempt_but_keeps_all_finals() -> None:
    responder = PreemptibleFocusResponder(
        answer_result("MySQL 中如何定位慢查询？")
    )
    subject = coordinator(responder, debounce_seconds=0.01)

    await subject.handle_transcript(
        transcript(Channel.INTERVIEWER, TranscriptPhase.FINAL, "在 MySQL 中。")
    )
    await responder.first_started.wait()
    await subject.handle_transcript(
        transcript(
            Channel.INTERVIEWER,
            TranscriptPhase.FINAL,
            "如何定位慢查询？",
            utterance_id="interviewer-2",
        )
    )
    await subject.wait_idle()

    assert responder.first_cancelled
    assert len(responder.calls) == 2
    assert "在 MySQL 中。如何定位慢查询？" in responder.calls[1]["prompt"]
    assert [turn.text for turn in subject.store.turns] == [
        "在 MySQL 中。",
        "如何定位慢查询？",
    ]
    assert subject.store.current_focus == "MySQL 中如何定位慢查询？"


@pytest.mark.asyncio
async def test_previous_focus_and_answer_are_in_next_prompt() -> None:
    responder = SequencedFocusResponder(
        (
            answer_result("Redis 为什么快？", "因为内存和 I/O 多路复用。"),
            answer_result("Redis 的 I/O 模型为什么高效？"),
        )
    )
    subject = coordinator(responder)

    await subject.handle_transcript(
        transcript(Channel.INTERVIEWER, TranscriptPhase.FINAL, "Redis 为什么快？")
    )
    await subject.wait_idle()
    await subject.handle_transcript(
        transcript(Channel.CANDIDATE, TranscriptPhase.FINAL, "我主要说了内存。")
    )
    await subject.handle_transcript(
        transcript(
            Channel.INTERVIEWER,
            TranscriptPhase.FINAL,
            "那 I/O 模型呢？",
            utterance_id="interviewer-2",
        )
    )
    await subject.wait_idle()

    second_prompt = responder.calls[1]["prompt"]
    assert "Q: Redis 为什么快？" in second_prompt
    assert "A: 因为内存和 I/O 多路复用。" in second_prompt
    assert "- C: 我主要说了内存。" in second_prompt
    assert "- I（最新）: 那 I/O 模型呢？" in second_prompt


@pytest.mark.asyncio
async def test_screenshot_focus_is_exclusive_and_defers_voice_focus() -> None:
    screenshot = BlockingScreenshotAnalyzer(
        AnswerResult(
            type="answer",
            question="实现两数之和",
            answer="使用哈希表保存已经遍历的数字。",
            code="def two_sum(nums, target):\n    return []",
        )
    )
    responder = FakeFocusResponder(answer_result("Redis 为什么快？"))
    sink = MemoryEventSink()
    status_updates: list[dict[str, object]] = []

    async def record_status(payload: dict[str, object]) -> None:
        status_updates.append(payload)

    subject = coordinator(
        responder,
        screenshot=screenshot,
        sink=sink,
        debounce_seconds=0.01,
    )

    accepted = await subject.handle_screenshot(
        screenshot_id="screen-1",
        image_data=b"fake-jpeg",
        mime_type="image/jpeg",
        storage_path="tasks/task-1/screenshots/screen-1.jpg",
        status_handler=record_status,
    )
    await screenshot.started.wait()
    await subject.handle_transcript(
        transcript(
            Channel.INTERVIEWER,
            TranscriptPhase.FINAL,
            "Redis 为什么快？",
            utterance_id="interviewer-after-screen",
        )
    )
    second_accepted = await subject.handle_screenshot(
        screenshot_id="screen-2",
        image_data=b"second",
        mime_type="image/jpeg",
        storage_path="tasks/task-1/screenshots/screen-2.jpg",
    )
    await asyncio.sleep(0.03)

    assert accepted
    assert not second_accepted
    assert subject.screenshot_focus_active
    assert not screenshot.cancelled
    assert responder.calls == []

    screenshot.release.set()
    await subject.wait_idle()

    screenshot_focus = subject.store.focuses[0]
    assert screenshot_focus.source is FocusSource.SCREENSHOT
    assert screenshot_focus.code.startswith("def two_sum")
    assert len(responder.calls) == 1
    assert "Redis 为什么快？" in responder.calls[0]["prompt"]
    assert not subject.screenshot_focus_active
    assert any(event.type == "focus.blocked" for event in sink.events)
    assert status_updates[-1]["status"] == "completed"
    assert float(status_updates[-1]["duration_ms"]) >= 0


@pytest.mark.asyncio
async def test_screenshot_focus_emits_structured_answer() -> None:
    screenshot = FakeScreenshotAnalyzer(
        AnswerResult(
            type="answer",
            question="反转链表",
            answer="使用三个指针迭代反转。时间 O(n)，空间 O(1)。",
            code="def reverse_list(head):\n    return head",
        )
    )
    sink = MemoryEventSink()
    subject = coordinator(
        FakeFocusResponder(wait_result()), screenshot=screenshot, sink=sink
    )

    await subject.handle_screenshot(
        screenshot_id="screen-structured",
        image_data=b"fake-image",
        mime_type="image/png",
        storage_path="tasks/task-1/screenshots/screen-structured.png",
    )
    await subject.wait_idle()

    completed = next(event for event in sink.events if event.type == "answer.completed")
    assert completed.payload["protocol_version"] == 2
    assert completed.payload["code"].startswith("def reverse_list")
    assert completed.payload["source"] == "SCREENSHOT"
