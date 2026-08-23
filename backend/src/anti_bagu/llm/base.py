from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from anti_bagu.interview.events import ModelResult


@dataclass(frozen=True, slots=True)
class ModelOutputFailure:
    attempt: int
    raw_content: str
    finish_reason: str | None
    error_type: str
    error_message: str


@dataclass(frozen=True, slots=True)
class InterviewResponse:
    result: ModelResult
    output_failures: tuple[ModelOutputFailure, ...] = ()


class ModelOutputRetriesExhausted(ValueError):
    def __init__(self, failures: tuple[ModelOutputFailure, ...]) -> None:
        self.failures = failures
        latest = failures[-1] if failures else None
        message = latest.error_message if latest else "model output validation failed"
        super().__init__(message)


class InterviewResponder(Protocol):
    async def respond(
        self,
        *,
        prompt: str,
        image_data: bytes | None = None,
        mime_type: str | None = None,
    ) -> ModelResult | InterviewResponse: ...
