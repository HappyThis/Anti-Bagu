from __future__ import annotations

import secrets
import time
from dataclasses import dataclass

from fastapi import WebSocket


@dataclass(slots=True)
class Pairing:
    token: str
    task_id: str
    owner_id: str
    expires_at: float
    websocket: WebSocket | None = None


class MobileHub:
    def __init__(self) -> None:
        self._by_token: dict[str, Pairing] = {}
        self._by_task: dict[str, Pairing] = {}

    def issue(self, task_id: str, owner_id: str, *, ttl_seconds: int = 600) -> Pairing:
        current = self._by_task.get(task_id)
        if current is not None and current.expires_at > time.time():
            return current
        token = secrets.token_urlsafe(24)
        pairing = Pairing(
            token=token,
            task_id=task_id,
            owner_id=owner_id,
            expires_at=time.time() + ttl_seconds,
        )
        self._by_token[token] = pairing
        self._by_task[task_id] = pairing
        return pairing

    def resolve(self, token: str) -> Pairing | None:
        pairing = self._by_token.get(token)
        if pairing is None:
            return None
        if pairing.expires_at <= time.time():
            self.revoke(pairing.task_id)
            return None
        return pairing

    def is_connected(self, task_id: str) -> bool:
        pairing = self._by_task.get(task_id)
        return (
            pairing is not None
            and pairing.expires_at > time.time()
            and pairing.websocket is not None
        )

    def attach(self, pairing: Pairing, websocket: WebSocket) -> None:
        pairing.websocket = websocket

    def detach(self, pairing: Pairing, websocket: WebSocket) -> None:
        if pairing.websocket is websocket:
            pairing.websocket = None

    def revoke(self, task_id: str) -> None:
        pairing = self._by_task.pop(task_id, None)
        if pairing is not None:
            self._by_token.pop(pairing.token, None)
