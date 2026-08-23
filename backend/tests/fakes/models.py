from __future__ import annotations

import asyncio

from anti_bagu.interview.events import ModelResult


class FakeFocusResponder:
    def __init__(self, result: ModelResult) -> None:
        self.result = result
        self.calls: list[dict[str, object]] = []

    async def respond(self, **kwargs) -> ModelResult:
        self.calls.append(kwargs)
        return self.result


class SequencedFocusResponder:
    def __init__(self, results: tuple[ModelResult, ...]) -> None:
        self.results = results
        self.calls: list[dict[str, object]] = []

    async def respond(self, **kwargs) -> ModelResult:
        index = len(self.calls)
        self.calls.append(kwargs)
        return self.results[min(index, len(self.results) - 1)]


class BlockingFocusResponder(FakeFocusResponder):
    def __init__(self, result: ModelResult) -> None:
        super().__init__(result)
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.cancelled = False

    async def respond(self, **kwargs) -> ModelResult:
        self.calls.append(kwargs)
        self.started.set()
        try:
            await self.release.wait()
        except asyncio.CancelledError:
            self.cancelled = True
            raise
        return self.result


class PreemptibleFocusResponder:
    def __init__(self, latest_result: ModelResult) -> None:
        self.latest_result = latest_result
        self.calls: list[dict[str, object]] = []
        self.first_started = asyncio.Event()
        self.first_cancelled = False
        self._never_release = asyncio.Event()

    async def respond(self, **kwargs) -> ModelResult:
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


class FakeScreenshotAnalyzer:
    def __init__(self, result: ModelResult) -> None:
        self.result = result
        self.calls: list[dict[str, object]] = []

    async def analyze(self, **kwargs) -> ModelResult:
        self.calls.append(kwargs)
        return self.result


class BlockingScreenshotAnalyzer(FakeScreenshotAnalyzer):
    def __init__(self, result: ModelResult) -> None:
        super().__init__(result)
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.cancelled = False

    async def analyze(self, **kwargs) -> ModelResult:
        self.calls.append(kwargs)
        self.started.set()
        try:
            await self.release.wait()
        except asyncio.CancelledError:
            self.cancelled = True
            raise
        return self.result
