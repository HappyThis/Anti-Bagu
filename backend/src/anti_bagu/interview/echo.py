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
            if length_ratio >= 0.8 and similarity >= self._similarity:
                return EchoMatch(
                    interviewer_event_id=interviewer.event_id,
                    similarity=similarity,
                    delay_seconds=delay,
                )
        return None

    @staticmethod
    def _audio_time(event: TranscriptEvent) -> float:
        return event.audio_ended_at if event.audio_ended_at is not None else event.created_at

    @staticmethod
    def _normalize(text: str) -> str:
        return "".join(character.casefold() for character in text if character.isalnum())
