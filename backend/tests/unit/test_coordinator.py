from __future__ import annotations

import asyncio

import pytest
from fakes.models import (
    BlockingFocusResponder,
    BlockingScreenshotAnalyzer,
    FakeFocusResponder,
    FakeScreenshotAnalyzer,
    PreemptibleFocusResponder,
    RoutedInterviewResponder,
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
from anti_bagu.llm.base import (
    InterviewResponse,
    ModelOutputFailure,
    ModelOutputRetriesExhausted,
)


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
        RoutedInterviewResponder(
            responder,
            screenshot or FakeScreenshotAnalyzer(wait_result()),
        ),
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


def output_failures() -> tuple[ModelOutputFailure, ...]:
    return (
        ModelOutputFailure(
            attempt=1,
            raw_content="first invalid output",
            finish_reason="stop",
            error_type="JSONDecodeError",
            error_message="Expecting value",
        ),
        ModelOutputFailure(
            attempt=2,
            raw_content="second invalid output",
            finish_reason="stop",
            error_type="JSONDecodeError",
            error_message="Expecting value",
        ),
    )


class AbandonedThenAnswerResponder:
    def __init__(self, result: AnswerResult) -> None:
        self.result = result
        self.calls: list[dict[str, object]] = []

    async def respond(self, **kwargs):
        self.calls.append(kwargs)
        if len(self.calls) == 1:
            raise ModelOutputRetriesExhausted(output_failures())
        return self.result


class AlwaysAbandonedResponder:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def respond(self, **kwargs):
        self.calls.append(kwargs)
        raise ModelOutputRetriesExhausted(output_failures())


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
    assert "# 上次分析后新增的对话" in second_prompt
    assert "- I: Redis 为什么快？" not in second_prompt
    assert "- C: 我主要说了内存。" in second_prompt
    assert "- I（最新）: 那 I/O 模型呢？" in second_prompt


@pytest.mark.asyncio
async def test_wait_advances_analysis_boundary_without_changing_focus() -> None:
    responder = SequencedFocusResponder(
        (wait_result(), answer_result("Redis 为什么快？"))
    )
    subject = coordinator(responder)

    await subject.handle_transcript(
        transcript(Channel.INTERVIEWER, TranscriptPhase.FINAL, "嗯，先等一下。")
    )
    await subject.wait_idle()
    await subject.handle_transcript(
        transcript(
            Channel.CANDIDATE,
            TranscriptPhase.FINAL,
            "好的。",
            utterance_id="candidate-after-wait",
        )
    )
    await subject.handle_transcript(
        transcript(
            Channel.INTERVIEWER,
            TranscriptPhase.FINAL,
            "Redis 为什么快？",
            utterance_id="interviewer-after-wait",
        )
    )
    await subject.wait_idle()

    assert len(responder.calls) == 2
    assert "嗯，先等一下" not in responder.calls[1]["prompt"]
    assert "- C: 好的。" in responder.calls[1]["prompt"]
    assert "- I（最新）: Redis 为什么快？" in responder.calls[1]["prompt"]


@pytest.mark.asyncio
async def test_identical_model_result_does_not_create_duplicate_focus() -> None:
    result = answer_result("什么是 MySQL 的幻读？", "幻读是范围查询出现新行。")
    responder = SequencedFocusResponder((result, result))
    sink = MemoryEventSink()
    subject = coordinator(responder, sink=sink)

    await subject.handle_transcript(
        transcript(Channel.INTERVIEWER, TranscriptPhase.FINAL, "什么是幻读？")
    )
    await subject.wait_idle()
    focus_id = subject.store.focuses[0].focus_id
    await subject.handle_transcript(
        transcript(
            Channel.INTERVIEWER,
            TranscriptPhase.FINAL,
            "嗯，对。",
            utterance_id="interviewer-confirmation",
        )
    )
    await subject.wait_idle()

    assert len(subject.store.focuses) == 1
    assert subject.store.focuses[0].focus_id == focus_id
    assert [event.type for event in sink.events].count("answer.completed") == 1
    assert [event.type for event in sink.events].count("focus.unchanged") == 1


@pytest.mark.asyncio
async def test_same_question_revises_current_focus_and_preserves_code() -> None:
    responder = SequencedFocusResponder(
        (
            answer_result(
                "反转链表",
                "使用三个指针。",
                "def reverse(head):\n    return head",
            ),
            answer_result("反转链表。", "补充说明需要保存 next 指针。"),
        )
    )
    sink = MemoryEventSink()
    subject = coordinator(responder, sink=sink)

    await subject.handle_transcript(
        transcript(Channel.INTERVIEWER, TranscriptPhase.FINAL, "怎么反转链表？")
    )
    await subject.wait_idle()
    focus_id = subject.store.focuses[0].focus_id
    await subject.handle_transcript(
        transcript(
            Channel.INTERVIEWER,
            TranscriptPhase.FINAL,
            "为什么要保存 next 指针？",
            utterance_id="interviewer-follow-up",
        )
    )
    await subject.wait_idle()

    assert len(subject.store.focuses) == 1
    current = subject.store.focuses[0]
    assert current.focus_id == focus_id
    assert current.recommended_answer == "补充说明需要保存 next 指针。"
    assert current.code == "def reverse(head):\n    return head"
    completed = [event for event in sink.events if event.type == "answer.completed"]
    assert len(completed) == 2
    assert {event.payload["focus_id"] for event in completed} == {focus_id}
    updates = [event for event in sink.events if event.type == "focus.updated"]
    assert updates[-1].payload["update_kind"] == "revised"


@pytest.mark.asyncio
async def test_new_question_creates_a_new_focus_card() -> None:
    responder = SequencedFocusResponder(
        (
            answer_result("Redis 为什么快？"),
            answer_result("HashMap 的底层结构是什么？"),
        )
    )
    subject = coordinator(responder)

    await subject.handle_transcript(
        transcript(Channel.INTERVIEWER, TranscriptPhase.FINAL, "Redis 为什么快？")
    )
    await subject.wait_idle()
    await subject.handle_transcript(
        transcript(
            Channel.INTERVIEWER,
            TranscriptPhase.FINAL,
            "HashMap 的底层结构是什么？",
            utterance_id="interviewer-new-topic",
        )
    )
    await subject.wait_idle()

    assert [focus.question for focus in subject.store.focuses] == [
        "Redis 为什么快？",
        "HashMap 的底层结构是什么？",
    ]


@pytest.mark.asyncio
async def test_abandoned_voice_focus_keeps_watermark_and_product_state_unchanged() -> None:
    responder = AbandonedThenAnswerResponder(answer_result("HashMap 是什么？"))
    sink = MemoryEventSink()
    subject = coordinator(responder, sink=sink)

    await subject.handle_transcript(
        transcript(Channel.INTERVIEWER, TranscriptPhase.FINAL, "Redis 为什么快？")
    )
    await subject.wait_idle()

    assert subject.store.focuses == ()
    assert [event.type for event in sink.events].count("focus.abandoned") == 1
    assert [event.type for event in sink.events].count("internal.llm.output_invalid") == 2
    assert "focus.error" not in [event.type for event in sink.events]
    assert "answer.completed" not in [event.type for event in sink.events]

    await subject.handle_transcript(
        transcript(
            Channel.INTERVIEWER,
            TranscriptPhase.FINAL,
            "HashMap 是什么？",
            utterance_id="interviewer-after-abandoned",
        )
    )
    await subject.wait_idle()

    assert len(responder.calls) == 2
    assert "Redis 为什么快？" in responder.calls[1]["prompt"]
    assert "HashMap 是什么？" in responder.calls[1]["prompt"]
    assert subject.store.current_focus == "HashMap 是什么？"


@pytest.mark.asyncio
async def test_successful_retry_records_diagnostics_and_commits_normally() -> None:
    response = InterviewResponse(
        result=answer_result("Redis 为什么快？"),
        output_failures=output_failures()[:1],
    )
    sink = MemoryEventSink()
    subject = coordinator(FakeFocusResponder(response), sink=sink)

    await subject.handle_transcript(
        transcript(Channel.INTERVIEWER, TranscriptPhase.FINAL, "Redis 为什么快？")
    )
    await subject.wait_idle()

    lifecycle = [event.type for event in sink.events]
    assert lifecycle.count("internal.llm.output_invalid") == 1
    assert lifecycle.count("focus.retry_succeeded") == 1
    assert lifecycle.count("answer.completed") == 1
    assert subject.store.current_focus == "Redis 为什么快？"


@pytest.mark.asyncio
async def test_abandoned_screenshot_leaves_no_focus_and_releases_exclusive_state() -> None:
    screenshot = AlwaysAbandonedResponder()
    sink = MemoryEventSink()
    statuses: list[dict[str, object]] = []

    async def record_status(payload: dict[str, object]) -> None:
        statuses.append(payload)

    subject = coordinator(
        FakeFocusResponder(wait_result()), screenshot=screenshot, sink=sink
    )

    await subject.handle_screenshot(
        screenshot_id="screen-abandoned",
        image_data=b"image",
        mime_type="image/jpeg",
        storage_path="tasks/task/screenshots/screen-abandoned.jpg",
        status_handler=record_status,
    )
    await subject.wait_idle()

    assert subject.store.focuses == ()
    assert not subject.screenshot_focus_active
    assert statuses[-1]["status"] == "abandoned"
    lifecycle = [event.type for event in sink.events]
    assert lifecycle.count("focus.abandoned") == 1
    assert lifecycle.count("internal.llm.output_invalid") == 2
    assert "answer.completed" not in lifecycle
    assert "error" not in lifecycle


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
