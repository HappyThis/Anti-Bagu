from __future__ import annotations

import json
import struct
from pathlib import Path
from typing import BinaryIO


class PCMArchive:
    """Append-only task audio archive with a small channel manifest."""

    def __init__(
        self,
        storage_dir: Path,
        task_id: str,
        channel: str,
        *,
        sample_rate: int,
        channels: int,
    ) -> None:
        self.directory = storage_dir / "tasks" / task_id / "audio"
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path = self.directory / f"{channel}.pcm"
        self.manifest_path = self.directory / f"{channel}.json"
        self.sample_rate = sample_rate
        self.channels = channels
        self._handle: BinaryIO = self.path.open("ab")
        self._first_captured_at: float | None = None
        self._last_captured_at: float | None = None
        self._frames = 0

    def append(self, pcm: bytes, *, captured_at: float) -> None:
        if self._first_captured_at is None:
            self._first_captured_at = captured_at
        self._last_captured_at = captured_at
        self._handle.write(pcm)
        self._frames += 1
        if self._frames % 50 == 0:
            self._handle.flush()

    def close(self) -> None:
        if self._handle.closed:
            return
        self._handle.flush()
        self._handle.close()
        manifest = {
            "sample_rate": self.sample_rate,
            "channels": self.channels,
            "sample_format": "pcm_s16le",
            "bytes": self.path.stat().st_size,
            "first_captured_at": self._first_captured_at,
            "last_captured_at": self._last_captured_at,
        }
        self.manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )


def wav_header(*, pcm_bytes: int, sample_rate: int = 16_000, channels: int = 1) -> bytes:
    bits_per_sample = 16
    block_align = channels * bits_per_sample // 8
    byte_rate = sample_rate * block_align
    return struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        pcm_bytes + 36,
        b"WAVE",
        b"fmt ",
        16,
        1,
        channels,
        sample_rate,
        byte_rate,
        block_align,
        bits_per_sample,
        b"data",
        pcm_bytes,
    )
