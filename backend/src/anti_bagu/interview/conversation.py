from __future__ import annotations

from anti_bagu.interview.events import (
    AnswerMode,
    AnswerStatus,
    Channel,
    CommittedFocus,
    ContentKind,
    ConversationTurn,
    FocusSource,
    TranscriptEvent,
)


class ConversationStore:
    """Complete in-memory final-turn log plus committed Focus history."""

    def __init__(self) -> None:
        self._turns: list[ConversationTurn] = []
        self._focuses: list[CommittedFocus] = []
        self._next_turn_id = 1
        self.revision = 0

    @property
    def turns(self) -> tuple[ConversationTurn, ...]:
        return tuple(self._turns)

    @property
    def focuses(self) -> tuple[CommittedFocus, ...]:
        return tuple(self._focuses)

    @property
    def current_focus(self) -> str:
        return self._focuses[-1].question if self._focuses else ""

    @property
    def current_recommended_answer(self) -> str:
        return self._focuses[-1].recommended_answer if self._focuses else ""

    @property
    def latest_turn_id(self) -> int:
        return self._turns[-1].turn_id if self._turns else 0

    def append_final(self, event: TranscriptEvent) -> ConversationTurn:
        if event.channel is Channel.INTERVIEWER:
            self.revision += 1

        turn = ConversationTurn(
            turn_id=self._next_turn_id,
            channel=event.channel,
            text=event.text.strip(),
            event_id=event.event_id,
            created_at=event.created_at,
        )
        self._next_turn_id += 1
        self._turns.append(turn)
        return turn

    def commit_focus(
        self,
        *,
        question: str,
        answer_mode: AnswerMode,
        recommended_answer: str,
        answer_status: AnswerStatus,
        source_end_turn_id: int,
        code: str = "",
        language: str = "",
        complexity: str = "",
        content_kind: ContentKind = ContentKind.KNOWLEDGE,
        source: FocusSource = FocusSource.VOICE,
        screenshot_id: str = "",
    ) -> CommittedFocus:
        previous_end = self._focuses[-1].source_end_turn_id if self._focuses else 0
        focus = CommittedFocus(
            question=question.strip(),
            answer_mode=answer_mode,
            recommended_answer=recommended_answer.strip(),
            code=code.strip(),
            language=language.strip(),
            complexity=complexity.strip(),
            content_kind=content_kind,
            source=source,
            screenshot_id=screenshot_id,
            answer_status=answer_status,
            source_start_turn_id=min(previous_end + 1, source_end_turn_id),
            source_end_turn_id=source_end_turn_id,
        )
        self._focuses.append(focus)
        return focus

    def append_focus_answer(self, focus_id: str, chunk: str) -> bool:
        focus = self._find_focus(focus_id)
        if focus is None:
            return False
        focus.recommended_answer += chunk
        return True

    def set_focus_answer_status(
        self, focus_id: str, status: AnswerStatus
    ) -> bool:
        focus = self._find_focus(focus_id)
        if focus is None:
            return False
        focus.answer_status = status
        return True

    def recent_conversation_payload(self, max_turns: int = 20) -> list[dict[str, str]]:
        return [
            {"role": turn.channel.value, "text": turn.text}
            for turn in self._turns[-max_turns:]
        ]

    def _find_focus(self, focus_id: str) -> CommittedFocus | None:
        for focus in reversed(self._focuses):
            if focus.focus_id == focus_id:
                return focus
        return None
