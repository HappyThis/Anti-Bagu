from __future__ import annotations

import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from anti_bagu.agent.authorization import AgentAuthorizationHub
from anti_bagu.agent.hub import AgentHub
from anti_bagu.api.routers import admin, agent_authorization, auth, realtime, tasks, user
from anti_bagu.auth.service import AuthService
from anti_bagu.config import Settings
from anti_bagu.credentials.service import CredentialCipher, ModelCredentialService
from anti_bagu.mobile.hub import MobileHub
from anti_bagu.persistence.database import create_database, create_schema
from anti_bagu.realtime.runtime import RuntimeRegistry
from anti_bagu.tasks.model_verifier import ModelVerifier
from anti_bagu.tasks.service import TaskService
from anti_bagu.telemetry.audit import DailyJsonlAudit


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
    database_engine, session_factory = create_database(active_settings.database_url)
    auth_service = AuthService(
        session_factory,
        web_session_days=active_settings.web_session_days,
        agent_token_days=active_settings.agent_token_days,
    )
    agent_hub = AgentHub()
    agent_authorizations = AgentAuthorizationHub()
    mobile_hub = MobileHub(
        active_settings.storage_dir.parent / "mobile-pairing.key"
    )
    model_credential_service = ModelCredentialService(
        session_factory,
        CredentialCipher(active_settings.credential_key_path),
    )
    model_verifier = ModelVerifier(active_settings)
    runtime_registry = RuntimeRegistry(
        active_settings, session_factory, audit
    )
    task_service = TaskService(
        session_factory,
        active_settings,
        agent_hub,
        mobile_hub,
        runtime_registry,
        model_verifier,
        model_credential_service,
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
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.audit = audit
    app.state.settings = active_settings
    app.state.database_engine = database_engine
    app.state.session_factory = session_factory
    app.state.auth_service = auth_service
    app.state.model_credential_service = model_credential_service
    app.state.model_verifier = model_verifier
    app.state.agent_hub = agent_hub
    app.state.agent_authorizations = agent_authorizations
    app.state.mobile_hub = mobile_hub
    app.state.runtime_registry = runtime_registry
    app.state.task_service = task_service

    app.include_router(auth.router)
    app.include_router(agent_authorization.router)
    app.include_router(tasks.router)
    app.include_router(user.router)
    app.include_router(admin.router)
    app.include_router(realtime.router)

    @app.get("/health")
    async def health() -> dict[str, object]:
        return {
            "status": "ok",
            "model_mode": "per_user",
            "audit_log_date": time.strftime("%Y-%m-%d"),
            "audit_dropped_events": audit.dropped,
            "database_configured": bool(active_settings.database_url),
            "agent_connections": agent_hub.connection_count,
            "active_task_runtimes": runtime_registry.active_count,
        }

    return app
