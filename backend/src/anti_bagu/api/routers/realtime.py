from __future__ import annotations

import asyncio
import base64
import binascii
import logging
import time
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from anti_bagu.agent.hub import AgentUnavailable
from anti_bagu.asr.qwen_streaming import QwenStreamingASRSession
from anti_bagu.audio.protocol import AudioFramePacket, AudioMetadata, pcm_level
from anti_bagu.interview.events import Channel, RealtimeEvent
from anti_bagu.persistence.audio_archive import PCMArchive
from anti_bagu.persistence.models import AgentDevice, Task, TaskEvent, User

LOGGER = logging.getLogger(__name__)
router = APIRouter(tags=["realtime"])


@router.websocket("/ws/agent")
async def agent_control(websocket: WebSocket) -> None:
    token = _websocket_token(websocket)
    user = await websocket.app.state.auth_service.resolve(token or "", kind="agent")
    if user is None:
        await websocket.close(code=4401, reason="invalid agent token")
        return
    await websocket.accept()
    device_payload: dict[str, object] = {}
    try:
        hello = await asyncio.wait_for(websocket.receive_json(), timeout=10)
        if hello.get("type") != "agent.hello":
            await websocket.close(code=4400, reason="agent.hello required")
            return
        device_payload = dict(hello.get("device") or {})
        device_payload.setdefault("device_key", "default-macos")
        device_payload.setdefault("name", "macOS Agent")
        device_payload.setdefault("platform", "macOS")
        device_payload.setdefault("agent_version", "unknown")
        await websocket.app.state.agent_hub.register(user.id, websocket, device_payload)
        await _upsert_device(websocket, user, device_payload, status="online")
        await websocket.send_json(
            {
                "type": "agent.ready",
                "heartbeat_interval_seconds": 20,
                "server_time": time.time(),
            }
        )
        while True:
            payload = await websocket.receive_json()
            if payload.get("type") == "screenshot.submit":
                await _handle_agent_screenshot(websocket, user, payload)
                continue
            websocket.app.state.agent_hub.handle_message(user.id, payload)
            if payload.get("type") == "agent.heartbeat":
                await websocket.send_json({"type": "agent.heartbeat.ack", "at": time.time()})
    except (WebSocketDisconnect, asyncio.CancelledError, TimeoutError):
        pass
    finally:
        await websocket.app.state.agent_hub.unregister(user.id, websocket)
        await _upsert_device(websocket, user, device_payload, status="offline")
        await _pause_running_tasks(websocket, user)


@router.websocket("/ws/tasks/{task_id}/ui")
async def task_ui(websocket: WebSocket, task_id: str) -> None:
    token = _websocket_token(websocket)
    user = await websocket.app.state.auth_service.resolve(token or "", kind="web")
    task = await _authorized_task(websocket, task_id, user)
    if task is None:
        await websocket.close(code=4403, reason="task access denied")
        return
    runtime = await websocket.app.state.runtime_registry.get(task_id)
    await websocket.accept()
    await websocket.send_json(
        RealtimeEvent(
            type="session.status",
            session_id=task_id,
            conversation_revision=runtime.coordinator.store.revision,
            payload={"status": task.status},
        ).model_dump(mode="json")
    )
    await _send_answer_history(websocket, task_id)
    receive_task: asyncio.Task[dict[str, object]] | None = None
    try:
        async with runtime.event_hub.subscribe() as queue:
            receive_task = asyncio.create_task(websocket.receive())
            while True:
                event_task = asyncio.create_task(queue.get())
                done, _ = await asyncio.wait(
                    {receive_task, event_task}, return_when=asyncio.FIRST_COMPLETED
                )
                if receive_task in done:
                    message = receive_task.result()
                    if message["type"] == "websocket.disconnect":
                        event_task.cancel()
                        await asyncio.gather(event_task, return_exceptions=True)
                        return
                    receive_task = asyncio.create_task(websocket.receive())
                if event_task in done:
                    await websocket.send_json(event_task.result().model_dump(mode="json"))
                else:
                    event_task.cancel()
                    await asyncio.gather(event_task, return_exceptions=True)
    except (WebSocketDisconnect, asyncio.CancelledError):
        pass
    finally:
        if receive_task is not None and not receive_task.done():
            receive_task.cancel()
            await asyncio.gather(receive_task, return_exceptions=True)


@router.websocket("/ws/mobile/{pairing_token}")
async def mobile_answers(websocket: WebSocket, pairing_token: str) -> None:
    pairing = websocket.app.state.mobile_hub.resolve(pairing_token)
    if pairing is None:
        await websocket.close(code=4404, reason="pairing expired")
        return
    runtime = await websocket.app.state.runtime_registry.get(pairing.task_id)
    await websocket.accept()
    websocket.app.state.mobile_hub.attach(pairing, websocket)
    await websocket.send_json(
        {
            "type": "mobile.paired",
            "task_id": pairing.task_id,
            "expires_at": pairing.expires_at,
        }
    )
    await _send_answer_history(websocket, pairing.task_id)
    try:
        async with runtime.event_hub.subscribe() as queue:
            while True:
                event = await queue.get()
                if event.type in {
                    "focus.updated",
                    "answer.started",
                    "answer.delta",
                    "answer.completed",
                    "answer.cancelled",
                    "task.status",
                    "screenshot.accepted",
                    "screenshot.focus.released",
                    "error",
                }:
                    await websocket.send_json(event.model_dump(mode="json"))
    except (WebSocketDisconnect, asyncio.CancelledError):
        pass
    finally:
        websocket.app.state.mobile_hub.detach(pairing, websocket)


@router.websocket("/ws/tasks/{task_id}/audio/{channel}")
async def task_audio(websocket: WebSocket, task_id: str, channel: Channel) -> None:
    token = _websocket_token(websocket)
    user = await websocket.app.state.auth_service.resolve(token or "", kind="agent")
    task = await _authorized_task(websocket, task_id, user)
    if task is None:
        await websocket.close(code=4403, reason="task access denied")
        return
    if task.status != "running":
        await websocket.close(code=4410, reason="task is not running")
        return
    runtime = await websocket.app.state.runtime_registry.get(task_id)
    await websocket.accept()
    if not runtime.dashscope_api_key:
        await websocket.close(code=4409, reason="task preflight has not configured ASR")
        return
    await _stream_audio(websocket, channel, runtime)


async def _stream_audio(websocket: WebSocket, channel: Channel, runtime) -> None:
    frame_count = 0
    asr_session: QwenStreamingASRSession | None = None
    archive: PCMArchive | None = None
    try:
        metadata = AudioMetadata.model_validate_json(await websocket.receive_text())
        archive = PCMArchive(
            runtime.settings.storage_dir,
            runtime.task_id,
            channel.value,
            sample_rate=metadata.sample_rate,
            channels=metadata.channels,
        )

        async def connect_asr() -> QwenStreamingASRSession:
            session = QwenStreamingASRSession(
                channel=channel,
                api_key=runtime.dashscope_api_key,
                ws_url=runtime.settings.dashscope_ws_url,
                model=runtime.settings.asr_model,
                transcript_handler=runtime.coordinator.handle_transcript,
                sample_rate=metadata.sample_rate,
                frame_duration_ms=metadata.frame_duration_ms,
            )
            await session.start()
            return session

        asr_session = await connect_asr()
        await runtime.event_hub.publish(
            RealtimeEvent(
                type="audio.connected",
                session_id=runtime.task_id,
                conversation_revision=runtime.coordinator.store.revision,
                payload={"channel": channel.value},
            )
        )
        while True:
            packet = AudioFramePacket.decode(await websocket.receive_bytes(), metadata)
            archive.append(packet.pcm, captured_at=packet.captured_at)
            received_at = time.time()
            rms, peak = pcm_level(packet.pcm)
            frame_count += 1
            await asr_session.send_audio(packet.pcm, captured_at=packet.captured_at)
            await runtime.event_hub.publish(
                RealtimeEvent(
                    type="audio.level",
                    session_id=runtime.task_id,
                    conversation_revision=runtime.coordinator.store.revision,
                    payload={"channel": channel.value, "rms": rms, "peak": peak},
                )
            )
            if frame_count % 5 == 0:
                key = "systemAudio" if channel is Channel.INTERVIEWER else "microphone"
                await runtime.event_hub.publish(
                    RealtimeEvent(
                        type="latency.updated",
                        session_id=runtime.task_id,
                        conversation_revision=runtime.coordinator.store.revision,
                        payload={
                            key: max(0.0, (received_at - packet.captured_at) * 1000)
                        },
                    )
                )
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        LOGGER.exception("Task audio pipeline failed for %s", channel.value)
        await runtime.event_hub.publish(
            RealtimeEvent(
                type="error",
                session_id=runtime.task_id,
                conversation_revision=runtime.coordinator.store.revision,
                payload={"message": str(exc), "operation": f"audio.{channel.value}"},
            )
        )
    finally:
        if asr_session is not None:
            await asr_session.close()
        if archive is not None:
            archive.close()
        await runtime.event_hub.publish(
            RealtimeEvent(
                type="audio.disconnected",
                session_id=runtime.task_id,
                conversation_revision=runtime.coordinator.store.revision,
                payload={"channel": channel.value, "frames_received": frame_count},
            )
        )


async def _handle_agent_screenshot(
    websocket: WebSocket,
    user: User,
    payload: dict[str, object],
) -> None:
    request_id = str(payload.get("request_id") or uuid.uuid4())
    task_id = str(payload.get("task_id") or "")

    async def reply(status: str, message: str = "") -> None:
        await websocket.send_json(
            {
                "type": "screenshot.result",
                "request_id": request_id,
                "task_id": task_id,
                "status": status,
                "message": message,
            }
        )

    task = await _authorized_task(websocket, task_id, user)
    if task is None or task.status != "running":
        await reply("rejected", "No running interview is available for screenshots.")
        return

    runtime = await websocket.app.state.runtime_registry.get(task_id)
    if runtime.coordinator.screenshot_focus_active:
        await reply("busy", "The previous screenshot is still being analyzed.")
        return

    mime_type = str(payload.get("mime_type") or "image/jpeg").lower()
    extensions = {"image/jpeg": "jpg", "image/png": "png"}
    extension = extensions.get(mime_type)
    if extension is None:
        await reply("rejected", "Only JPEG and PNG screenshots are supported.")
        return

    encoded = payload.get("image_base64")
    if not isinstance(encoded, str) or not encoded:
        await reply("rejected", "The screenshot payload is empty.")
        return
    if len(encoded) > 12_000_000:
        await reply("rejected", "The screenshot is too large.")
        return
    try:
        image_data = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError):
        await reply("rejected", "The screenshot payload is invalid.")
        return
    if not image_data or len(image_data) > 8_000_000:
        await reply("rejected", "The screenshot is too large.")
        return

    screenshot_id = str(uuid.uuid4())
    relative_path = f"tasks/{task_id}/screenshots/{screenshot_id}.{extension}"
    absolute_path = websocket.app.state.settings.storage_dir / relative_path

    def persist() -> None:
        absolute_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = absolute_path.with_suffix(f".{extension}.tmp")
        temporary.write_bytes(image_data)
        temporary.replace(absolute_path)

    await asyncio.to_thread(persist)

    async def notify_agent(status_payload: dict[str, object]) -> None:
        try:
            await websocket.app.state.agent_hub.send(
                user.id,
                {
                    **status_payload,
                    "request_id": request_id,
                    "task_id": task_id,
                },
            )
        except AgentUnavailable:
            pass

    accepted = await runtime.coordinator.handle_screenshot(
        screenshot_id=screenshot_id,
        image_data=image_data,
        mime_type=mime_type,
        storage_path=relative_path,
        status_handler=notify_agent,
    )
    if not accepted:
        await asyncio.to_thread(absolute_path.unlink, True)
        await reply("busy", "The previous screenshot is still being analyzed.")
        return
    await reply("accepted", "Screenshot captured. Analysis has started.")


async def _send_answer_history(websocket: WebSocket, task_id: str) -> None:
    async with websocket.app.state.session_factory() as session:
        rows = (
            await session.scalars(
                select(TaskEvent)
                .where(TaskEvent.task_id == task_id)
                .where(
                    TaskEvent.event_type.in_(
                        ("focus.updated", "answer.completed", "answer.cancelled")
                    )
                )
                .order_by(TaskEvent.created_at.asc(), TaskEvent.id.asc())
                .limit(500)
            )
        ).all()
    for row in rows:
        await websocket.send_json(
            RealtimeEvent(
                type=row.event_type,
                event_id=row.event_id,
                session_id=task_id,
                conversation_revision=row.conversation_revision,
                created_at=row.created_at.timestamp(),
                payload=row.payload,
            ).model_dump(mode="json")
        )


def _websocket_token(websocket: WebSocket) -> str | None:
    value = websocket.headers.get("authorization")
    if value:
        scheme, _, token = value.partition(" ")
        if scheme.lower() == "bearer" and token:
            return token.strip()
    return (
        websocket.cookies.get("anti_bagu_session")
        or websocket.query_params.get("token")
    )


async def _authorized_task(websocket: WebSocket, task_id: str, user: User | None):
    if user is None:
        return None
    async with websocket.app.state.session_factory() as session:
        task = await session.get(Task, task_id)
        if task is None:
            return None
        if task.deleted_at is not None and user.role != "admin":
            return None
        if user.role != "admin" and task.owner_id != user.id:
            return None
        return task


async def _upsert_device(
    websocket: WebSocket, user: User, payload: dict[str, object], *, status: str
) -> None:
    device_key = str(payload.get("device_key") or "default-macos")
    async with websocket.app.state.session_factory() as session:
        device = await session.scalar(
            select(AgentDevice)
            .where(AgentDevice.user_id == user.id)
            .where(AgentDevice.device_key == device_key)
        )
        if device is None:
            device = AgentDevice(
                user_id=user.id,
                device_key=device_key,
                name=str(payload.get("name") or "macOS Agent"),
            )
            session.add(device)
        device.name = str(payload.get("name") or device.name)
        device.platform = str(payload.get("platform") or "macOS")
        device.agent_version = str(payload.get("agent_version") or "unknown")
        device.status = status
        device.last_seen_at = datetime.now(UTC)
        device.metadata_json = {
            key: value
            for key, value in payload.items()
            if key not in {"token", "api_key"}
        }
        await session.commit()


async def _pause_running_tasks(websocket: WebSocket, user: User) -> None:
    async with websocket.app.state.session_factory() as session:
        tasks = (
            await session.scalars(
                select(Task)
                .where(Task.owner_id == user.id)
                .where(Task.status == "running")
            )
        ).all()
        for task in tasks:
            task.status = "paused"
        if tasks:
            await session.commit()
