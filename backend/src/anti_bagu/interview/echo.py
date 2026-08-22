from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from difflib import SequenceMatcher

from anti_bagu.interview.events import Channel, TranscriptEvent


@dataclass(frozen=True, slots=True)
class EchoMatch:
    interviewer_event_id: str
    similarity: float
    delay_seconds: float
    overlap_ratio: float


class CrossChannelEchoSuppressor:
    """Detect interviewer audio leaking into the candidate microphone channel."""

    def __init__(self, *, window_seconds: float = 3.0, similarity: float = 0.94) -> None:
        self._window_seconds = window_seconds
        self._similarity = similarity
        self._interviewer_finals: deque[TranscriptEvent] = deque(maxlen=12)

    def remember_interviewer(self, event: TranscriptEvent) -> None:
        if event.channel is Channel.INTERVIEWER and event.text.strip():
            self._interviewer_finals.append(event)

    def match_candidate(self, event: TranscriptEvent) -> EchoMatch | None:
        if event.channel is not Channel.CANDIDATE:
            return None
        candidate = self._normalize(event.text)
        if len(candidate) < 4:
            return None

        candidate_at = self._audio_time(event)
        for interviewer in reversed(self._interviewer_finals):
            delay = candidate_at - self._audio_time(interviewer)
            if abs(delay) > self._window_seconds:
                continue
            reference = self._normalize(interviewer.text)
            if len(reference) < 4:
                continue
            length_ratio = min(len(candidate), len(reference)) / max(
                len(candidate), len(reference)
            )
            similarity = (
                1.0
                if candidate == reference
                else SequenceMatcher(None, candidate, reference).ratio()
            )
            overlap_ratio = self._overlap_ratio(interviewer, event)
            strong_text_match = length_ratio >= 0.8 and similarity >= self._similarity
            overlapping_audio_match = (
                overlap_ratio >= 0.6 and length_ratio >= 0.65 and similarity >= 0.6
            )
            if strong_text_match or overlapping_audio_match:
                return EchoMatch(
                    interviewer_event_id=interviewer.event_id,
                    similarity=similarity,
                    delay_seconds=delay,
                    overlap_ratio=overlap_ratio,
                )
        return None

    @staticmethod
    def _audio_time(event: TranscriptEvent) -> float:
        return event.audio_ended_at if event.audio_ended_at is not None else event.created_at

    @staticmethod
    def _overlap_ratio(first: TranscriptEvent, second: TranscriptEvent) -> float:
        if (
            first.audio_started_at is None
            or first.audio_ended_at is None
            or second.audio_started_at is None
            or second.audio_ended_at is None
        ):
            return 0.0
        overlap = max(
            0.0,
            min(first.audio_ended_at, second.audio_ended_at)
            - max(first.audio_started_at, second.audio_started_at),
        )
        shorter = min(
            first.audio_ended_at - first.audio_started_at,
            second.audio_ended_at - second.audio_started_at,
        )
        return overlap / shorter if shorter > 0 else 0.0

    @staticmethod
    def _normalize(text: str) -> str:
        return "".join(character.casefold() for character in text if character.isalnum())
