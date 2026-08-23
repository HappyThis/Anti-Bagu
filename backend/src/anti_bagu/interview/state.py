from enum import StrEnum


class SessionState(StrEnum):
    LISTENING = "LISTENING"
    EVALUATING = "EVALUATING"
    ANSWERING = "ANSWERING"
