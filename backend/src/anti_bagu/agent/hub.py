from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from fastapi import WebSocket


class AgentUnavailable(RuntimeError):
    pass


@dataclass(slots=True)
class AgentConnection:
    user_id: str
    websocket: WebSocket
    device: dict[str, Any]
    connected_at: float = field(default_factory=time.time)
    last_seen_at: float = field(default_factory=time.time)
    active_task_id: str | None = None


class AgentHub:
    """One active desktop Agent per beta user, with request/response correlation."""

    def __init__(self) -> None:
        self._connections: dict[str, AgentConnection] = {}
        self._pending: dict[
            str, tuple[str, asyncio.Future[dict[str, Any]]]
        ] = {}
        self._lock = asyncio.Lock()

    def get(self, user_id: str) -> AgentConnection | None:
        return self._connections.get(user_id)

    def is_connected(self, user_id: str) -> bool:
        return user_id in self._connections

    async def register(
        self, user_id: str, websocket: WebSocket, device: dict[str, Any]
    ) -> AgentConnection:
        connection = AgentConnection(user_id=user_id, websocket=websocket, device=device)
        async with self._lock:
            previous = self._connections.get(user_id)
            self._connections[user_id] = connection
        if previous is not None and previous.websocket is not websocket:
            try:
                await previous.websocket.close(code=4001, reason="new agent connected")
            except RuntimeError:
                pass
        return connection

    async def unregister(self, user_id: str, websocket: WebSocket) -> None:
        async with self._lock:
            current = self._connections.get(user_id)
            if current is not None and current.websocket is websocket:
                self._connections.pop(user_id, None)
        for request_id, (pending_user_id, future) in tuple(self._pending.items()):
            if pending_user_id == user_id:
                if not future.done():
                    future.set_exception(AgentUnavailable("桌面 Agent 已断开"))
                self._pending.pop(request_id, None)

    async def send(self, user_id: str, payload: dict[str, Any]) -> None:
        connection = self._connections.get(user_id)
        if connection is None:
            raise AgentUnavailable("桌面 Agent 未连接")
        await connection.websocket.send_json(payload)

    async def request_preflight(
        self, user_id: str, task_id: str, *, timeout_seconds: float = 15.0
    ) -> dict[str, Any]:
        request_id = str(uuid.uuid4())
        loop = asyncio.get_running_loop()
        future: asyncio.Future[dict[str, Any]] = loop.create_future()
        self._pending[request_id] = (user_id, future)
        try:
            await self.send(
                user_id,
                {
                    "type": "preflight.request",
                    "request_id": request_id,
                    "task_id": task_id,
                },
            )
            return await asyncio.wait_for(future, timeout=timeout_seconds)
        except TimeoutError as exc:
            raise AgentUnavailable("桌面 Agent 预检响应超时") from exc
        finally:
            self._pending.pop(request_id, None)

    def handle_message(self, user_id: str, payload: dict[str, Any]) -> None:
        connection = self._connections.get(user_id)
        if connection is not None:
            connection.last_seen_at = time.time()
        if payload.get("type") != "preflight.result":
            return
        request_id = str(payload.get("request_id", ""))
        pending = self._pending.get(request_id)
        if pending is not None:
            pending_user_id, future = pending
            if pending_user_id == user_id and not future.done():
                future.set_result(payload)

    @property
    def connection_count(self) -> int:
        return len(self._connections)
