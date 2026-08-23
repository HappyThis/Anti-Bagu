from __future__ import annotations

from typing import Protocol

from anti_bagu.interview.events import ModelResult


class FocusResponder(Protocol):
    async def respond(self, *, prompt: str) -> ModelResult: ...


class ScreenshotAnalyzer(Protocol):
    async def analyze(
        self,
        *,
        prompt: str,
        image_data: bytes,
        mime_type: str,
    ) -> ModelResult: ...
