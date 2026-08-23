from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from anti_bagu.interview.events import FocusResult, ScreenshotFocusResult


class FakeFocusResponder:
    def __init__(self, result: FocusResult) -> None:
        self.result = result
        self.calls: list[dict[str, object]] = []

    async def respond(self, **kwargs) -> FocusResult:
        self.calls.append(kwargs)
        return self.result


class SequencedFocusResponder:
    def __init__(self, results: tuple[FocusResult, ...]) -> None:
        self.results = results
        self.calls: list[dict[str, object]] = []

    async def respond(self, **kwargs) -> FocusResult:
        index = len(self.calls)
        self.calls.append(kwargs)
        return self.results[min(index, len(self.results) - 1)]


class BlockingFocusResponder(FakeFocusResponder):
    def __init__(self, result: FocusResult) -> None:
        super().__init__(result)
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.cancelled = False

    async def respond(self, **kwargs) -> FocusResult:
        self.calls.append(kwargs)
        self.started.set()
        try:
            await self.release.wait()
        except asyncio.CancelledError:
            self.cancelled = True
            raise
        return self.result


class PreemptibleFocusResponder:
    def __init__(self, latest_result: FocusResult) -> None:
        self.latest_result = latest_result
        self.calls: list[dict[str, object]] = []
        self.first_started = asyncio.Event()
        self.first_cancelled = False
        self._never_release = asyncio.Event()

    async def respond(self, **kwargs) -> FocusResult:
        index = len(self.calls)
        self.calls.append(kwargs)
        if index == 0:
            self.first_started.set()
            try:
                await self._never_release.wait()
            except asyncio.CancelledError:
                self.first_cancelled = True
                raise
        return self.latest_result


class FakeThinkingAnswerer:
    def __init__(self, chunks: tuple[str, ...] = ("思考答案",)) -> None:
        self.chunks = chunks
        self.calls: list[dict[str, object]] = []

    async def stream_answer(self, **kwargs) -> AsyncIterator[str]:
        self.calls.append(kwargs)
        for chunk in self.chunks:
            yield chunk


class BlockingThinkingAnswerer(FakeThinkingAnswerer):
    def __init__(self) -> None:
        super().__init__()
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.cancelled = False

    async def stream_answer(self, **kwargs) -> AsyncIterator[str]:
        self.calls.append(kwargs)
        yield "已经显示的部分。"
        self.started.set()
        try:
            await self.release.wait()
        except asyncio.CancelledError:
            self.cancelled = True
            raise
        yield "后续内容。"


class FakeScreenshotAnalyzer:
    def __init__(self, result: ScreenshotFocusResult) -> None:
        self.result = result
        self.calls: list[dict[str, object]] = []

    async def analyze(self, **kwargs) -> ScreenshotFocusResult:
        self.calls.append(kwargs)
        return self.result


class BlockingScreenshotAnalyzer(FakeScreenshotAnalyzer):
    def __init__(self, result: ScreenshotFocusResult) -> None:
        super().__init__(result)
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.cancelled = False

    async def analyze(self, **kwargs) -> ScreenshotFocusResult:
        self.calls.append(kwargs)
        self.started.set()
        try:
            await self.release.wait()
        except asyncio.CancelledError:
            self.cancelled = True
            raise
        return self.result
