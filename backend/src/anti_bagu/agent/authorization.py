from __future__ import annotations

import asyncio
import secrets
import string
import time
import uuid
from dataclasses import dataclass

from anti_bagu.auth.service import IssuedSession
from anti_bagu.core.security import hash_token


@dataclass(slots=True)
class BrowserAuthorization:
    request_id: str
    device_secret_hash: str
    user_code: str
    expires_at: float
    status: str = "pending"
    agent_token: str | None = None
    token_expires_at: str | None = None
    username: str | None = None


class AgentAuthorizationHub:
    """Short-lived browser authorization requests for the desktop helper."""

    def __init__(self, *, ttl_seconds: int = 300) -> None:
        self._ttl_seconds = ttl_seconds
        self._by_id: dict[str, BrowserAuthorization] = {}
        self._by_code: dict[str, BrowserAuthorization] = {}
        self._lock = asyncio.Lock()

    async def create(self) -> tuple[BrowserAuthorization, str]:
        async with self._lock:
            self._remove_expired()
            request_id = str(uuid.uuid4())
            device_secret = secrets.token_urlsafe(32)
            user_code = self._new_user_code()
            request = BrowserAuthorization(
                request_id=request_id,
                device_secret_hash=hash_token(device_secret),
                user_code=user_code,
                expires_at=time.time() + self._ttl_seconds,
            )
            self._by_id[request_id] = request
            self._by_code[user_code] = request
            return request, device_secret

    async def approve(
        self, user_code: str, issued: IssuedSession
    ) -> BrowserAuthorization | None:
        async with self._lock:
            request = self._by_code.get(user_code.upper())
            if request is None or request.expires_at <= time.time():
                return None
            if request.status != "pending":
                return None
            request.status = "approved"
            request.agent_token = issued.token
            request.token_expires_at = issued.expires_at.isoformat()
            request.username = issued.user.username
            return request

    async def poll(
        self, request_id: str, device_secret: str
    ) -> dict[str, str | float | None] | None:
        async with self._lock:
            request = self._by_id.get(request_id)
            if request is None or not secrets.compare_digest(
                request.device_secret_hash, hash_token(device_secret)
            ):
                return None
            if request.expires_at <= time.time():
                request.status = "expired"
            result: dict[str, str | float | None] = {
                "status": request.status,
                "expires_at": request.expires_at,
            }
            if request.status == "approved":
                result.update(
                    {
                        "token": request.agent_token,
                        "token_expires_at": request.token_expires_at,
                        "username": request.username,
                    }
                )
                request.agent_token = None
                request.status = "consumed"
            return result

    async def cancel(self, user_code: str) -> BrowserAuthorization | None:
        async with self._lock:
            request = self._by_code.get(user_code.upper())
            if request is None or request.expires_at <= time.time():
                return None
            if request.status != "pending":
                return None
            request.status = "cancelled"
            return request

    def _new_user_code(self) -> str:
        alphabet = string.ascii_uppercase + string.digits
        while True:
            code = "".join(secrets.choice(alphabet) for _ in range(8))
            if code not in self._by_code:
                return code

    def _remove_expired(self) -> None:
        now = time.time()
        for request_id, request in tuple(self._by_id.items()):
            if request.expires_at <= now:
                self._by_id.pop(request_id, None)
                self._by_code.pop(request.user_code, None)
