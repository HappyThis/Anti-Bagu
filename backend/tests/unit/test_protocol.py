import pytest
from pydantic import ValidationError

from anti_bagu.audio.protocol import AudioFramePacket, AudioMetadata, pcm_level
from anti_bagu.interview.events import AnswerMode, FocusAction, FocusResult


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


def test_wait_protocol_rejects_answer() -> None:
    with pytest.raises(ValidationError):
        FocusResult(
            action=FocusAction.WAIT,
            answer_mode=AnswerMode.NONE,
            answer="不应出现",
        )
