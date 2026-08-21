from __future__ import annotations

from typing import Protocol

from anti_bagu.interview.events import Channel


class ASRSession(Protocol):
    channel: Channel

    async def start(self) -> None: ...

    async def send_audio(self, pcm: bytes) -> None: ...

    async def close(self) -> None: ...
