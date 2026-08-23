from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from dataclasses import dataclass
from pathlib import Path

from fastapi import WebSocket


@dataclass(slots=True)
class Pairing:
    token: str
    task_id: str
    owner_id: str
    expires_at: float
    websocket: WebSocket | None = None


class MobileHub:
    """Task-scoped signed mobile links plus ephemeral connection presence."""

    def __init__(self, secret_path: Path, *, ttl_seconds: int = 86_400) -> None:
        self._secret_path = secret_path
        self._ttl_seconds = ttl_seconds
        self._secret: bytes | None = None
        self._by_token: dict[str, Pairing] = {}
        self._by_task: dict[str, Pairing] = {}
        self._revoked_tasks: set[str] = set()

    def issue(self, task_id: str, owner_id: str) -> Pairing:
        current = self._by_task.get(task_id)
        if current is not None and current.expires_at > time.time():
            return current
        self._revoked_tasks.discard(task_id)
        expires_at = time.time() + self._ttl_seconds
        token = self._encode(
            {
                "v": 1,
                "task_id": task_id,
                "owner_id": owner_id,
                "expires_at": expires_at,
                "nonce": secrets.token_urlsafe(12),
            }
        )
        pairing = Pairing(
            token=token,
            task_id=task_id,
            owner_id=owner_id,
            expires_at=expires_at,
        )
        self._by_token[token] = pairing
        self._by_task[task_id] = pairing
        return pairing

    def resolve(self, token: str) -> Pairing | None:
        current = self._by_token.get(token)
        if current is not None:
            if current.task_id in self._revoked_tasks or current.expires_at <= time.time():
                return None
            return current
        payload = self._decode(token)
        if payload is None:
            return None
        task_id = str(payload.get("task_id") or "")
        owner_id = str(payload.get("owner_id") or "")
        expires_at = float(payload.get("expires_at") or 0)
        if (
            not task_id
            or not owner_id
            or task_id in self._revoked_tasks
            or expires_at <= time.time()
        ):
            return None
        pairing = Pairing(
            token=token,
            task_id=task_id,
            owner_id=owner_id,
            expires_at=expires_at,
        )
        self._by_token[token] = pairing
        self._by_task[task_id] = pairing
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
        self._revoked_tasks.add(task_id)
        pairing = self._by_task.pop(task_id, None)
        if pairing is not None:
            self._by_token.pop(pairing.token, None)

    def _encode(self, payload: dict[str, object]) -> str:
        body = self._b64encode(
            json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
        )
        signature = self._b64encode(
            hmac.new(self._get_secret(), body.encode(), hashlib.sha256).digest()
        )
        return f"{body}.{signature}"

    def _decode(self, token: str) -> dict[str, object] | None:
        body, separator, signature = token.partition(".")
        if not separator or not body or not signature:
            return None
        expected = self._b64encode(
            hmac.new(self._get_secret(), body.encode(), hashlib.sha256).digest()
        )
        if not hmac.compare_digest(signature, expected):
            return None
        try:
            payload = json.loads(self._b64decode(body))
        except (ValueError, json.JSONDecodeError):
            return None
        if not isinstance(payload, dict) or payload.get("v") != 1:
            return None
        return payload

    def _get_secret(self) -> bytes:
        if self._secret is None:
            self._secret = self._load_or_create_secret()
        return self._secret

    def _load_or_create_secret(self) -> bytes:
        self._secret_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            descriptor = os.open(
                self._secret_path,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
            )
        except FileExistsError:
            pass
        else:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(os.urandom(32))
        secret = self._secret_path.read_bytes()
        if len(secret) != 32:
            raise RuntimeError("mobile pairing key must contain exactly 32 bytes")
        return secret

    @staticmethod
    def _b64encode(value: bytes) -> str:
        return base64.urlsafe_b64encode(value).decode().rstrip("=")

    @staticmethod
    def _b64decode(value: str) -> bytes:
        padding = "=" * (-len(value) % 4)
        return base64.urlsafe_b64decode(f"{value}{padding}")
