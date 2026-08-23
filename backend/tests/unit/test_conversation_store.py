from anti_bagu.interview.conversation import ConversationStore
from anti_bagu.interview.events import (
    Channel,
    TranscriptEvent,
    TranscriptPhase,
)


def final(channel: Channel, text: str) -> TranscriptEvent:
    return TranscriptEvent(
        channel=channel,
        phase=TranscriptPhase.FINAL,
        text=text,
    )


def test_final_turn_log_is_complete_and_monotonic() -> None:
    store = ConversationStore()
    for index in range(100):
        store.append_final(
            final(
                Channel.INTERVIEWER if index % 2 else Channel.CANDIDATE,
                f"对话 {index}",
            )
        )

    assert len(store.turns) == 100
    assert [turn.turn_id for turn in store.turns] == list(range(1, 101))


def test_committed_focus_keeps_visible_answer_and_source_range() -> None:
    store = ConversationStore()
    store.append_final(final(Channel.INTERVIEWER, "设计一个限流器"))
    focus = store.commit_focus(
        question="设计一个限流器",
        recommended_answer="先使用令牌桶。",
        source_end_turn_id=1,
    )

    assert store.current_focus == "设计一个限流器"
    assert store.current_recommended_answer == "先使用令牌桶。"
    assert (focus.source_start_turn_id, focus.source_end_turn_id) == (1, 1)
