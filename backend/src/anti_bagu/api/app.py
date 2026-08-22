from __future__ import annotations

import asyncio
import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from anti_bagu.agent.hub import AgentHub
from anti_bagu.api.event_hub import EventHub
from anti_bagu.api.routers import admin, auth, realtime, tasks, user
from anti_bagu.asr.qwen_streaming import QwenStreamingASRSession
from anti_bagu.audio.protocol import AudioFramePacket, AudioMetadata, pcm_level
from anti_bagu.auth.service import AuthService
from anti_bagu.config import Settings
from anti_bagu.interview.context import FocusPromptBuilder, TokenEstimator
from anti_bagu.interview.coordinator import InterviewCoordinator
from anti_bagu.interview.events import Channel, RealtimeEvent, TranscriptEvent
from anti_bagu.llm.deepseek import (
    FOCUS_SYSTEM_PROMPT,
    DeepSeekFocusResponder,
    DeepSeekThinkingAnswerer,
    UnavailableFocusResponder,
    UnavailableThinkingAnswerer,
)
from anti_bagu.mobile.hub import MobileHub
from anti_bagu.persistence.database import create_database, create_schema
from anti_bagu.realtime.runtime import RuntimeRegistry
from anti_bagu.tasks.model_verifier import ModelVerifier
from anti_bagu.tasks.service import TaskService
from anti_bagu.telemetry.audit import DailyJsonlAudit

LOGGER = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    active_settings = settings or Settings.from_env()
    session_id = str(uuid.uuid4())
    audit = DailyJsonlAudit(
        active_settings.audit_log_dir,
        session_id=session_id,
        include_text=active_settings.audit_include_text,
        ring_size=active_settings.audit_ring_size,
        queue_size=active_settings.audit_queue_size,
    )
    event_hub = EventHub(audit=audit)
    database_engine, session_factory = create_database(active_settings.database_url)
    auth_service = AuthService(
        session_factory,
        web_session_days=active_settings.web_session_days,
        agent_token_days=active_settings.agent_token_days,
    )
    agent_hub = AgentHub()
    mobile_hub = MobileHub()
    runtime_registry = RuntimeRegistry(
        active_settings, session_factory, audit
    )
    task_service = TaskService(
        session_factory,
        active_settings,
        agent_hub,
        mobile_hub,
        runtime_registry,
        ModelVerifier(active_settings),
    )

    if active_settings.deepseek_api_key:
        focus_responder = DeepSeekFocusResponder(
            active_settings.deepseek_api_key,
            active_settings.deepseek_base_url,
            active_settings.deepseek_model,
        )
        thinking_answerer = DeepSeekThinkingAnswerer(
            active_settings.deepseek_api_key,
            active_settings.deepseek_base_url,
            active_settings.deepseek_model,
        )
    else:
        focus_responder = UnavailableFocusResponder()
        thinking_answerer = UnavailableThinkingAnswerer()

    prompt_builder = FocusPromptBuilder(
        system_prompt=FOCUS_SYSTEM_PROMPT,
        target_tokens=active_settings.focus_prompt_target_tokens,
        dialogue_target_tokens=active_settings.focus_dialogue_target_tokens,
        history_target_tokens=active_settings.focus_history_target_tokens,
        estimator=TokenEstimator(active_settings.focus_characters_per_token),
    )
    coordinator = InterviewCoordinator(
        focus_responder,
        thinking_answerer,
        event_hub,
        prompt_builder,
        session_id=session_id,
        debounce_seconds=active_settings.focus_debounce_ms / 1000,
        max_coalesce_seconds=active_settings.focus_max_coalesce_ms / 1000,
        focus_timeout_seconds=active_settings.focus_timeout_seconds,
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        if active_settings.auto_create_schema:
            await create_schema(database_engine)
        await auth_service.ensure_admin(
            active_settings.admin_username, active_settings.admin_password
        )
        await audit.start()
        audit.emit(
            "server.started",
            payload={
                "model": active_settings.deepseek_model,
                "asr_model": active_settings.asr_model,
                "include_text": active_settings.audit_include_text,
            },
        )
        try:
            yield
        finally:
            await runtime_registry.close()
            await coordinator.close()
            audit.emit("server.stopped")
            await audit.close()
            await database_engine.dispose()

    app = FastAPI(
        title="Anti-Bagu Realtime Core",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(active_settings.cors_origins),
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.coordinator = coordinator
    app.state.event_hub = event_hub
    app.state.audit = audit
    app.state.settings = active_settings
    app.state.database_engine = database_engine
    app.state.session_factory = session_factory
    app.state.auth_service = auth_service
    app.state.agent_hub = agent_hub
    app.state.mobile_hub = mobile_hub
    app.state.runtime_registry = runtime_registry
    app.state.task_service = task_service

    app.include_router(auth.router)
    app.include_router(tasks.router)
    app.include_router(user.router)
    app.include_router(admin.router)
    app.include_router(realtime.router)

    @app.get("/health")
    async def health() -> dict[str, object]:
        return {
            "status": "ok",
            "model_configured": bool(active_settings.deepseek_api_key),
            "session_id": coordinator.session_id,
            "conversation_revision": coordinator.store.revision,
            "audit_log_date": time.strftime("%Y-%m-%d"),
            "audit_dropped_events": audit.dropped,
            "database_configured": bool(active_settings.database_url),
            "agent_connections": agent_hub.connection_count,
            "active_task_runtimes": runtime_registry.active_count,
        }

    @app.get("/api/debug/events")
    async def debug_events(
        limit: int = Query(default=200, ge=1, le=1_000),
        event_prefix: str | None = None,
    ) -> dict[str, object]:
        return {
            "events": audit.recent(limit=limit, event_prefix=event_prefix),
            "dropped": audit.dropped,
            "text_included": audit.include_text,
        }

    @app.post("/api/transcripts", status_code=202)
    async def submit_transcript(event: TranscriptEvent) -> dict[str, object]:
        await coordinator.handle_transcript(event)
        return {
            "accepted": True,
            "conversation_revision": coordinator.store.revision,
        }

    @app.websocket("/ws/ui")
    async def ui_events(websocket: WebSocket) -> None:
        await websocket.accept()
        connection_id = str(uuid.uuid4())
        audit.emit(
            "ui.connected",
            payload={"connection_id": connection_id},
            conversation_revision=coordinator.store.revision,
        )
        receive_task: asyncio.Task[dict[str, object]] | None = None
        try:
            async with event_hub.subscribe() as queue:
                receive_task = asyncio.create_task(websocket.receive())
                while True:
                    event_task = asyncio.create_task(queue.get())
                    done, _ = await asyncio.wait(
                        {receive_task, event_task},
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    if receive_task in done:
                        message = receive_task.result()
                        if message["type"] == "websocket.disconnect":
                            event_task.cancel()
                            await asyncio.gather(event_task, return_exceptions=True)
                            return
                        receive_task = asyncio.create_task(websocket.receive())
                    if event_task in done:
                        event = event_task.result()
                        await websocket.send_json(event.model_dump(mode="json"))
                    else:
                        event_task.cancel()
                        await asyncio.gather(event_task, return_exceptions=True)
        except (WebSocketDisconnect, asyncio.CancelledError):
            return
        finally:
            audit.emit(
                "ui.disconnected",
                payload={"connection_id": connection_id},
                conversation_revision=coordinator.store.revision,
            )
            if receive_task is not None and not receive_task.done():
                receive_task.cancel()
                await asyncio.gather(receive_task, return_exceptions=True)

    @app.websocket("/ws/audio/{channel}")
    async def audio_frames(websocket: WebSocket, channel: Channel) -> None:
        await websocket.accept()
        frame_count = 0
        asr_session: QwenStreamingASRSession | None = None
        try:
            if not active_settings.dashscope_api_key:
                await websocket.close(code=1011, reason="DASHSCOPE_API_KEY is not configured")
                return
            metadata = AudioMetadata.model_validate_json(await websocket.receive_text())

            async def connect_asr() -> QwenStreamingASRSession:
                session = QwenStreamingASRSession(
                    channel=channel,
                    api_key=active_settings.dashscope_api_key,
                    ws_url=active_settings.dashscope_ws_url,
                    model=active_settings.asr_model,
                    transcript_handler=coordinator.handle_transcript,
                    sample_rate=metadata.sample_rate,
                    frame_duration_ms=metadata.frame_duration_ms,
                )
                await session.start()
                await event_hub.publish(
                    RealtimeEvent(
                        type="asr.connected",
                        session_id=coordinator.session_id,
                        conversation_revision=coordinator.store.revision,
                        payload={
                            "channel": channel.value,
                            "model": active_settings.asr_model,
                        },
                    )
                )
                return session

            asr_session = await connect_asr()
            await event_hub.publish(
                RealtimeEvent(
                    type="audio.connected",
                    session_id=coordinator.session_id,
                    conversation_revision=coordinator.store.revision,
                    payload={
                        "channel": channel.value,
                        "frame_bytes": metadata.expected_frame_bytes,
                        "packet_bytes": metadata.expected_packet_bytes,
                    },
                )
            )
            while True:
                packet = AudioFramePacket.decode(
                    await websocket.receive_bytes(), metadata
                )
                received_at = time.time()
                rms, peak = pcm_level(packet.pcm)
                transport_ms = max(0.0, (received_at - packet.captured_at) * 1000)
                frame_count += 1
                try:
                    await asr_session.send_audio(
                        packet.pcm, captured_at=packet.captured_at
                    )
                except Exception as asr_error:
                    LOGGER.warning(
                        "ASR stream failed for %s; reconnecting: %s",
                        channel.value,
                        asr_error,
                    )
                    await event_hub.publish(
                        RealtimeEvent(
                            type="asr.reconnecting",
                            session_id=coordinator.session_id,
                            conversation_revision=coordinator.store.revision,
                            payload={"channel": channel.value},
                        )
                    )
                    await asr_session.close()
                    last_error: Exception = asr_error
                    for attempt in range(1, 4):
                        try:
                            await asyncio.sleep(0.2 * attempt)
                            asr_session = await connect_asr()
                            await asr_session.send_audio(
                                packet.pcm, captured_at=packet.captured_at
                            )
                            await event_hub.publish(
                                RealtimeEvent(
                                    type="asr.reconnected",
                                    session_id=coordinator.session_id,
                                    conversation_revision=coordinator.store.revision,
                                    payload={"channel": channel.value},
                                )
                            )
                            break
                        except Exception as reconnect_error:
                            last_error = reconnect_error
                            audit.emit(
                                "asr.reconnect.failed",
                                level="WARNING",
                                payload={
                                    "channel": channel.value,
                                    "attempt": attempt,
                                    "error_type": type(reconnect_error).__name__,
                                    "message": str(reconnect_error),
                                },
                                conversation_revision=coordinator.store.revision,
                            )
                    else:
                        raise RuntimeError(
                            f"ASR reconnect failed for {channel.value}: {last_error}"
                        ) from last_error
                await event_hub.publish(
                    RealtimeEvent(
                        type="audio.level",
                        session_id=coordinator.session_id,
                        conversation_revision=coordinator.store.revision,
                        payload={
                            "channel": channel.value,
                            "rms": rms,
                            "peak": peak,
                        },
                    )
                )
                if frame_count % 5 == 0:
                    latency_key = (
                        "systemAudio"
                        if channel is Channel.INTERVIEWER
                        else "microphone"
                    )
                    await event_hub.publish(
                        RealtimeEvent(
                            type="latency.updated",
                            session_id=coordinator.session_id,
                            conversation_revision=coordinator.store.revision,
                            payload={latency_key: transport_ms},
                        )
                    )
        except WebSocketDisconnect:
            pass
        except Exception as exc:
            LOGGER.exception("Audio pipeline failed for %s", channel.value)
            await event_hub.publish(
                RealtimeEvent(
                    type="error",
                    session_id=coordinator.session_id,
                    conversation_revision=coordinator.store.revision,
                    payload={
                        "message": str(exc),
                        "operation": f"audio.{channel.value}",
                    },
                )
            )
            try:
                await websocket.close(code=1011, reason="audio pipeline failed")
            except RuntimeError:
                pass
        finally:
            if asr_session is not None:
                await asr_session.close()
            await event_hub.publish(
                RealtimeEvent(
                    type="audio.disconnected",
                    session_id=coordinator.session_id,
                    conversation_revision=coordinator.store.revision,
                    payload={"channel": channel.value, "frames_received": frame_count},
                )
            )

    return app
