from __future__ import annotations

from typing import Protocol

from anti_bagu.interview.events import ModelResult


class InterviewResponder(Protocol):
    async def respond(
        self,
        *,
        prompt: str,
        image_data: bytes | None = None,
        mime_type: str | None = None,
    ) -> ModelResult: ...
