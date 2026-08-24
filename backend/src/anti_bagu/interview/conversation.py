from __future__ import annotations

from anti_bagu.interview.events import (
    Channel,
    CommittedFocus,
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
    def current_committed_focus(self) -> CommittedFocus | None:
        return self._focuses[-1] if self._focuses else None

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
        recommended_answer: str,
        source_end_turn_id: int,
        code: str | None = None,
        source: FocusSource = FocusSource.VOICE,
        screenshot_id: str = "",
    ) -> CommittedFocus:
        previous_end = self._focuses[-1].source_end_turn_id if self._focuses else 0
        focus = CommittedFocus(
            question=question.strip(),
            recommended_answer=recommended_answer.strip(),
            code=code.strip() if code else None,
            source=source,
            screenshot_id=screenshot_id,
            source_start_turn_id=min(previous_end + 1, source_end_turn_id),
            source_end_turn_id=source_end_turn_id,
        )
        self._focuses.append(focus)
        return focus

    def update_current_focus(
        self,
        *,
        recommended_answer: str,
        source_end_turn_id: int,
        code: str | None = None,
        source: FocusSource = FocusSource.VOICE,
        screenshot_id: str = "",
    ) -> CommittedFocus:
        current = self.current_committed_focus
        if current is None:
            raise RuntimeError("cannot update a missing Focus")
        updated = current.model_copy(
            update={
                "recommended_answer": recommended_answer.strip(),
                "code": code.strip() if code else current.code,
                "source": source,
                "screenshot_id": screenshot_id or current.screenshot_id,
                "source_end_turn_id": source_end_turn_id,
            }
        )
        self._focuses[-1] = updated
        return updated

    def recent_conversation_payload(self, max_turns: int = 20) -> list[dict[str, str]]:
        return [
            {"role": turn.channel.value, "text": turn.text}
            for turn in self._turns[-max_turns:]
        ]

    def restore(
        self,
        *,
        turns: tuple[ConversationTurn, ...],
        focuses: tuple[CommittedFocus, ...],
    ) -> None:
        self._turns = list(turns)
        self._focuses = list(focuses)
        self._next_turn_id = max((turn.turn_id for turn in turns), default=0) + 1
        self.revision = sum(turn.channel is Channel.INTERVIEWER for turn in turns)
