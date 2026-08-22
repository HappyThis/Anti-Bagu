from __future__ import annotations

import asyncio

import pytest
from fakes.models import (
    BlockingFocusResponder,
    BlockingThinkingAnswerer,
    FakeFocusResponder,
    FakeThinkingAnswerer,
    PreemptibleFocusResponder,
    SequencedFocusResponder,
)

from anti_bagu.interview.context import FocusPromptBuilder
from anti_bagu.interview.coordinator import InterviewCoordinator
from anti_bagu.interview.events import (
    AnswerMode,
    AnswerStatus,
    Channel,
    FocusAction,
    FocusResult,
    TranscriptEvent,
    TranscriptPhase,
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
    thinking=None,
    sink=None,
    debounce_seconds: float = 0,
) -> InterviewCoordinator:
    return InterviewCoordinator(
        responder,
        thinking or FakeThinkingAnswerer(),
        sink or MemoryEventSink(),
        FocusPromptBuilder(system_prompt="I 是面试官，C 是候选人。返回 JSON。"),
        debounce_seconds=debounce_seconds,
        max_coalesce_seconds=max(debounce_seconds * 4, 0.01),
    )


def wait_result() -> FocusResult:
    return FocusResult(action=FocusAction.WAIT, answer_mode=AnswerMode.NONE)


def fast_result(question: str, answer: str = "简短回答。") -> FocusResult:
    return FocusResult(
        action=FocusAction.RESPOND,
        answer_mode=AnswerMode.FAST,
        focus_question=question,
        answer=answer,
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
        fast_result("Redis 为什么快？", "因为内存和 I/O 多路复用。")
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
    assert subject.store.focuses[-1].answer_status is AnswerStatus.COMPLETED
    assert [event.type for event in sink.events].count("answer.completed") == 1
    lifecycle = [event.type for event in sink.events]
    assert "transcript.committed" in lifecycle
    assert "focus.window.started" in lifecycle
    assert "focus.window.fired" in lifecycle
    assert "focus.started" in lifecycle
    assert "focus.responded" in lifecycle


@pytest.mark.asyncio
async def test_two_quick_finals_share_one_debounced_request() -> None:
    responder = FakeFocusResponder(fast_result("MySQL 中如何定位慢查询？"))
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
    responder = BlockingFocusResponder(fast_result("什么是 AQS？"))
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
    responder = BlockingFocusResponder(fast_result("什么是 AQS？"))
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
        fast_result("MySQL 中如何定位慢查询？")
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
            fast_result("Redis 为什么快？", "因为内存和 I/O 多路复用。"),
            fast_result("Redis 的 I/O 模型为什么高效？"),
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
async def test_thinking_answer_is_saved_for_future_focus_context() -> None:
    responder = FakeFocusResponder(
        FocusResult(
            action=FocusAction.RESPOND,
            answer_mode=AnswerMode.THINK,
            focus_question="设计一个限流器",
        )
    )
    sink = MemoryEventSink()
    thinking = FakeThinkingAnswerer(("先使用令牌桶。", "再考虑分布式一致性。"))
    subject = coordinator(responder, thinking=thinking, sink=sink)

    await subject.handle_transcript(
        transcript(Channel.INTERVIEWER, TranscriptPhase.FINAL, "设计一个限流器")
    )
    await subject.wait_idle()

    committed = subject.store.focuses[-1]
    assert committed.recommended_answer == "先使用令牌桶。再考虑分布式一致性。"
    assert committed.answer_status is AnswerStatus.COMPLETED
    assert [event.type for event in sink.events].count("answer.delta") == 2


@pytest.mark.asyncio
async def test_new_committed_focus_cancels_old_thinking_answer() -> None:
    responder = SequencedFocusResponder(
        (
            FocusResult(
                action=FocusAction.RESPOND,
                answer_mode=AnswerMode.THINK,
                focus_question="设计一个限流器",
            ),
            fast_result("MySQL 中如何定位慢查询？"),
        )
    )
    thinking = BlockingThinkingAnswerer()
    subject = coordinator(responder, thinking=thinking, debounce_seconds=0.01)

    await subject.handle_transcript(
        transcript(Channel.INTERVIEWER, TranscriptPhase.FINAL, "设计一个限流器")
    )
    await thinking.started.wait()
    first_focus = subject.store.focuses[-1]
    await subject.handle_transcript(
        transcript(
            Channel.INTERVIEWER,
            TranscriptPhase.FINAL,
            "MySQL 中如何定位慢查询？",
            utterance_id="interviewer-2",
        )
    )
    await subject.wait_idle()

    assert thinking.cancelled
    assert first_focus.answer_status is AnswerStatus.INTERRUPTED
    assert first_focus.recommended_answer == "已经显示的部分。"
    assert subject.store.current_focus == "MySQL 中如何定位慢查询？"
