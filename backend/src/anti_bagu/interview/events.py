from __future__ import annotations

import time
import uuid
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Channel(StrEnum):
    INTERVIEWER = "interviewer"
    CANDIDATE = "candidate"


class TranscriptPhase(StrEnum):
    PARTIAL = "partial"
    FINAL = "final"


class FocusAction(StrEnum):
    WAIT = "WAIT"
    RESPOND = "RESPOND"


class AnswerMode(StrEnum):
    NONE = "NONE"
    FAST = "FAST"
    THINK = "THINK"


class AnswerStatus(StrEnum):
    GENERATING = "GENERATING"
    COMPLETED = "COMPLETED"
    INTERRUPTED = "INTERRUPTED"


class TranscriptEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    channel: Channel
    phase: TranscriptPhase
    text: str
    utterance_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    audio_started_at: float | None = None
    audio_ended_at: float | None = None
    created_at: float = Field(default_factory=time.time)


class ConversationTurn(BaseModel):
    turn_id: int
    channel: Channel
    text: str
    event_id: str
    created_at: float


class CommittedFocus(BaseModel):
    focus_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    question: str
    answer_mode: AnswerMode
    recommended_answer: str = ""
    answer_status: AnswerStatus
    source_start_turn_id: int
    source_end_turn_id: int
    created_at: float = Field(default_factory=time.time)


class FocusResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: FocusAction
    answer_mode: AnswerMode
    focus_question: str = ""
    answer: str = ""

    @model_validator(mode="after")
    def validate_protocol(self) -> FocusResult:
        if self.action is FocusAction.WAIT:
            if self.answer_mode is not AnswerMode.NONE:
                raise ValueError("WAIT requires answer_mode NONE")
            if self.focus_question or self.answer:
                raise ValueError("WAIT requires empty focus_question and answer")
            return self

        if not self.focus_question.strip():
            raise ValueError("RESPOND requires a focus_question")
        if self.answer_mode is AnswerMode.NONE:
            raise ValueError("RESPOND cannot use answer_mode NONE")
        if self.answer_mode is AnswerMode.FAST and not self.answer.strip():
            raise ValueError("FAST requires an answer")
        if self.answer_mode is AnswerMode.THINK and self.answer:
            raise ValueError("THINK requires an empty answer")
        return self


class RealtimeEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str
    conversation_revision: int = Field(ge=0)
    created_at: float = Field(default_factory=time.time)
    payload: dict[str, Any] = Field(default_factory=dict)
