import pytest
from pydantic import ValidationError

from anti_bagu.audio.protocol import AudioFramePacket, AudioMetadata, pcm_level
from anti_bagu.interview.events import (
    AnswerResult,
    WaitResult,
    parse_model_result_json,
)


def test_audio_metadata_accepts_v1_pcm_format() -> None:
    metadata = AudioMetadata()
    assert metadata.expected_frame_bytes == 3200
    assert metadata.expected_packet_bytes == 3208


def test_audio_packet_preserves_capture_timestamp_and_pcm() -> None:
    metadata = AudioMetadata()
    original = AudioFramePacket(captured_at=1_800_000_000.25, pcm=bytes(3200))
    decoded = AudioFramePacket.decode(original.encode(), metadata)

    assert decoded == original


def test_pcm_level_reports_silence() -> None:
    assert pcm_level(bytes(3200)) == (0.0, 0.0)


def test_wait_result_is_canonicalized() -> None:
    result = parse_model_result_json(
        '{"type":"wait","language":"python","answer":"ignored"}'
    )

    assert result == WaitResult(type="wait")
    assert result.model_dump() == {"type": "wait"}


def test_answer_result_always_requires_question_and_answer() -> None:
    result = AnswerResult(
        type="answer",
        question="实现两数之和",
        answer="使用哈希表。",
        code="def two_sum(nums, target): return []",
    )

    assert result.code is not None

    with pytest.raises(ValidationError):
        AnswerResult(type="answer", question="实现两数之和", answer="")
