from __future__ import annotations

import json
import re
import time
import uuid
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator


class Channel(StrEnum):
    INTERVIEWER = "interviewer"
    CANDIDATE = "candidate"


class TranscriptPhase(StrEnum):
    PARTIAL = "partial"
    FINAL = "final"


class FocusSource(StrEnum):
    VOICE = "VOICE"
    SCREENSHOT = "SCREENSHOT"


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
    recommended_answer: str = ""
    code: str | None = None
    source: FocusSource = FocusSource.VOICE
    screenshot_id: str = ""
    source_start_turn_id: int
    source_end_turn_id: int
    created_at: float = Field(default_factory=time.time)


class WaitResult(BaseModel):
    """Canonical no-answer result; harmless extra model fields are discarded."""

    model_config = ConfigDict(extra="ignore")

    type: Literal["wait"]


class AnswerResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["answer"]
    question: str
    answer: str
    code: str | None = None

    @model_validator(mode="after")
    def validate_answer(self) -> AnswerResult:
        self.question = self.question.strip()
        self.answer = self.answer.strip()
        self.code = self.code.strip() if self.code and self.code.strip() else None
        if self.code:
            self.answer = re.sub(
                r"```(?:python)?\s*[\s\S]*?```",
                "",
                self.answer,
                flags=re.IGNORECASE,
            ).strip()
            self.answer = re.sub(r"\n{3,}", "\n\n", self.answer)
        if not self.question:
            raise ValueError("answer requires a question")
        if not self.answer:
            raise ValueError("answer requires answer text")
        if len(self.question) > 60:
            raise ValueError(
                "question must be a short display title of at most 60 characters"
            )
        if len(self.answer) > 600:
            raise ValueError(
                "answer must be concise and at most 600 characters"
            )
        return self


ModelResult = Annotated[WaitResult | AnswerResult, Field(discriminator="type")]
MODEL_RESULT_ADAPTER = TypeAdapter(ModelResult)


def parse_model_result_json(content: str) -> ModelResult:
    payload = json.loads(content)
    if isinstance(payload, dict) and payload.get("type") == "wait":
        return WaitResult(type="wait")
    return MODEL_RESULT_ADAPTER.validate_python(payload)


class RealtimeEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str
    conversation_revision: int = Field(ge=0)
    created_at: float = Field(default_factory=time.time)
    payload: dict[str, Any] = Field(default_factory=dict)
