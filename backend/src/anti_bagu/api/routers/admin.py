from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from anti_bagu.api.dependencies import Principal, current_admin, get_auth_service, get_db
from anti_bagu.api.schemas import ActivationKeyCreateRequest, ActivationKeyView
from anti_bagu.auth.service import AuthService
from anti_bagu.persistence.models import ActivationKey, PlatformAudit, Task, User

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


@router.get("/overview")
async def overview(
    request: Request,
    _: Principal = Depends(current_admin),
    session: AsyncSession = Depends(get_db),
):
    now = datetime.now(UTC)
    user_count = await session.scalar(select(func.count()).select_from(User)) or 0
    key_count = await session.scalar(
        select(func.count()).select_from(ActivationKey).where(ActivationKey.status == "unused")
    ) or 0
    active_tasks = await session.scalar(
        select(func.count()).select_from(Task).where(Task.status.in_(("running", "paused")))
    ) or 0
    today_tasks = await session.scalar(
        select(func.count()).select_from(Task).where(Task.created_at >= now - timedelta(days=1))
    ) or 0
    events = (
        await session.scalars(
            select(PlatformAudit).order_by(PlatformAudit.created_at.desc()).limit(12)
        )
    ).all()
    return {
        "users": user_count,
        "available_keys": key_count,
        "active_tasks": active_tasks,
        "today_tasks": today_tasks,
        "agent_connections": request.app.state.agent_hub.connection_count,
        "active_runtimes": request.app.state.runtime_registry.active_count,
        "recent_events": [
            {
                "id": event.id,
                "action": event.action,
                "target_type": event.target_type,
                "target_id": event.target_id,
                "created_at": event.created_at,
            }
            for event in events
        ],
    }


@router.get("/activation-keys", response_model=list[ActivationKeyView])
async def activation_keys(
    _: Principal = Depends(current_admin),
    session: AsyncSession = Depends(get_db),
):
    rows = (
        await session.scalars(select(ActivationKey).order_by(ActivationKey.created_at.desc()))
    ).all()
    users = {
        user.id: user.username
        for user in (await session.scalars(select(User))).all()
    }
    return [
        ActivationKeyView(
            id=row.id,
            key_hint=row.key_hint,
            status=row.status,
            created_at=row.created_at,
            expires_at=row.expires_at,
            bound_username=users.get(row.used_by_id or ""),
        )
        for row in rows
    ]


@router.post("/activation-keys", response_model=ActivationKeyView)
async def create_activation_key(
    payload: ActivationKeyCreateRequest,
    principal: Principal = Depends(current_admin),
    auth: AuthService = Depends(get_auth_service),
):
    record, display_key = await auth.create_activation_key(
        actor=principal.user, valid_days=payload.valid_days
    )
    return ActivationKeyView(
        id=record.id,
        key_hint=record.key_hint,
        display_key=display_key,
        status=record.status,
        created_at=record.created_at,
        expires_at=record.expires_at,
    )


@router.post("/activation-keys/{key_id}/revoke")
async def revoke_activation_key(
    key_id: str,
    principal: Principal = Depends(current_admin),
    session: AsyncSession = Depends(get_db),
):
    record = await session.get(ActivationKey, key_id)
    if record is None:
        raise HTTPException(status_code=404, detail="激活密钥不存在")
    if record.status == "unused":
        record.status = "revoked"
        session.add(
            PlatformAudit(
                actor_user_id=principal.user.id,
                action="activation_key.revoked",
                target_type="activation_key",
                target_id=record.id,
            )
        )
        await session.commit()
    return {"ok": True}


@router.get("/users")
async def users(
    _: Principal = Depends(current_admin),
    session: AsyncSession = Depends(get_db),
):
    task_counts = dict(
        (await session.execute(select(Task.owner_id, func.count()).group_by(Task.owner_id))).all()
    )
    rows = (await session.scalars(select(User).order_by(User.created_at.desc()))).all()
    return [
        {
            "id": row.id,
            "username": row.username,
            "display_name": row.display_name,
            "role": row.role,
            "status": row.status,
            "created_at": row.created_at,
            "task_count": task_counts.get(row.id, 0),
        }
        for row in rows
    ]


@router.patch("/users/{user_id}")
async def update_user(
    user_id: str,
    status_value: str = Query(alias="status", pattern="^(active|disabled)$"),
    principal: Principal = Depends(current_admin),
    session: AsyncSession = Depends(get_db),
):
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    if user.id == principal.user.id and status_value == "disabled":
        raise HTTPException(status_code=400, detail="不能停用当前管理员")
    user.status = status_value
    await session.commit()
    return {"ok": True, "status": user.status}


@router.get("/tasks")
async def tasks(
    _: Principal = Depends(current_admin),
    session: AsyncSession = Depends(get_db),
):
    rows = (
        await session.execute(
            select(Task, User.username)
            .join(User, User.id == Task.owner_id)
            .order_by(Task.updated_at.desc())
        )
    ).all()
    return [
        {
            "id": task.id,
            "name": task.name,
            "username": username,
            "status": task.status,
            "updated_at": task.updated_at,
            "created_at": task.created_at,
        }
        for task, username in rows
    ]


@router.get("/system")
async def system_status(
    request: Request,
    _: Principal = Depends(current_admin),
):
    load = os.getloadavg() if hasattr(os, "getloadavg") else (0.0, 0.0, 0.0)
    return {
        "status": "ok",
        "load_average": load,
        "agent_connections": request.app.state.agent_hub.connection_count,
        "active_runtimes": request.app.state.runtime_registry.active_count,
        "audit_dropped_events": request.app.state.audit.dropped,
        "database": "connected",
        "storage_dir": str(request.app.state.settings.storage_dir),
    }


@router.get("/logs")
async def recent_logs(
    request: Request,
    limit: int = Query(default=100, ge=1, le=1_000),
    _: Principal = Depends(current_admin),
):
    return {
        "events": request.app.state.audit.recent(limit=limit),
        "dropped": request.app.state.audit.dropped,
    }
