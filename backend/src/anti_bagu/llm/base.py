from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol

from anti_bagu.interview.events import FocusResult


class FocusResponder(Protocol):
    async def respond(self, *, prompt: str) -> FocusResult: ...


class ThinkingAnswerer(Protocol):
    def stream_answer(
        self,
        *,
        question: str,
        conversation: list[dict[str, str]],
    ) -> AsyncIterator[str]: ...
