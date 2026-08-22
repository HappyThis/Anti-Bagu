from __future__ import annotations

import json

from anti_bagu.persistence.audio_archive import PCMArchive, wav_header


def test_pcm_archive_appends_audio_and_writes_manifest(tmp_path) -> None:
    archive = PCMArchive(
        tmp_path,
        "task-1",
        "candidate",
        sample_rate=16_000,
        channels=1,
    )
    archive.append(b"\x00\x01" * 1_600, captured_at=10.0)
    archive.append(b"\x02\x03" * 1_600, captured_at=10.1)
    archive.close()

    pcm = tmp_path / "tasks" / "task-1" / "audio" / "candidate.pcm"
    manifest = json.loads(
        (tmp_path / "tasks" / "task-1" / "audio" / "candidate.json").read_text()
    )
    assert pcm.stat().st_size == 6_400
    assert manifest["bytes"] == 6_400
    assert manifest["first_captured_at"] == 10.0
    assert manifest["last_captured_at"] == 10.1


def test_wav_header_describes_pcm_payload() -> None:
    header = wav_header(pcm_bytes=3_200)

    assert len(header) == 44
    assert header[:4] == b"RIFF"
    assert header[8:12] == b"WAVE"
    assert header[-4:] == (3_200).to_bytes(4, "little")
