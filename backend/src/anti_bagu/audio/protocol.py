from __future__ import annotations

import math
import struct
from array import array
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class AudioMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sample_rate: Literal[16000] = 16000
    channels: Literal[1] = 1
    sample_format: Literal["pcm_s16le"] = "pcm_s16le"
    frame_duration_ms: int = Field(default=100, ge=20, le=200)

    @property
    def expected_frame_bytes(self) -> int:
        return self.sample_rate * self.channels * 2 * self.frame_duration_ms // 1000

    @property
    def expected_packet_bytes(self) -> int:
        return AudioFramePacket.HEADER.size + self.expected_frame_bytes


@dataclass(frozen=True, slots=True)
class AudioFramePacket:
    captured_at: float
    pcm: bytes

    HEADER = struct.Struct("<d")

    @classmethod
    def decode(cls, packet: bytes, metadata: AudioMetadata) -> AudioFramePacket:
        if len(packet) != metadata.expected_packet_bytes:
            raise ValueError(
                f"expected {metadata.expected_packet_bytes} packet bytes, got {len(packet)}"
            )
        (captured_at,) = cls.HEADER.unpack_from(packet)
        if not math.isfinite(captured_at) or captured_at <= 0:
            raise ValueError("invalid capture timestamp")
        return cls(captured_at=captured_at, pcm=packet[cls.HEADER.size :])

    def encode(self) -> bytes:
        return self.HEADER.pack(self.captured_at) + self.pcm


def pcm_level(pcm: bytes) -> tuple[float, float]:
    samples = array("h")
    samples.frombytes(pcm)
    if not samples:
        return 0.0, 0.0
    peak = max(abs(sample) for sample in samples) / 32768.0
    square_mean = sum(sample * sample for sample in samples) / len(samples)
    rms = math.sqrt(square_mean) / 32768.0
    return min(rms, 1.0), min(peak, 1.0)
