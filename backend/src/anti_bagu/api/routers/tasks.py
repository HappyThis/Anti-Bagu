from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from anti_bagu.agent.hub import AgentUnavailable
from anti_bagu.api.dependencies import Principal, current_principal, get_db
from anti_bagu.api.schemas import (
    CreateTaskRequest,
    PreflightResponse,
    TaskEventView,
    TaskView,
    UpdateTaskRequest,
)
from anti_bagu.persistence.models import TaskEvent
from anti_bagu.tasks.service import TaskError, TaskService

router = APIRouter(prefix="/api/v1/tasks", tags=["tasks"])


def task_service(request: Request) -> TaskService:
    return request.app.state.task_service


@router.get("", response_model=list[TaskView])
async def list_tasks(
    principal: Principal = Depends(current_principal),
    service: TaskService = Depends(task_service),
):
    return await service.list_for(principal.user)


@router.post("", response_model=TaskView, status_code=status.HTTP_201_CREATED)
async def create_task(
    payload: CreateTaskRequest,
    principal: Principal = Depends(current_principal),
    service: TaskService = Depends(task_service),
):
    return await service.create(
        principal.user,
        name=payload.name,
        mode=payload.mode,
        mobile_required=payload.mobile_required,
    )


@router.get("/{task_id}", response_model=TaskView)
async def get_task(
    task_id: str,
    principal: Principal = Depends(current_principal),
    service: TaskService = Depends(task_service),
):
    return await _task_call(service.get_for(task_id, principal.user))


@router.patch("/{task_id}", response_model=TaskView)
async def update_task(
    task_id: str,
    payload: UpdateTaskRequest,
    principal: Principal = Depends(current_principal),
    service: TaskService = Depends(task_service),
):
    if payload.name is None:
        return await _task_call(service.get_for(task_id, principal.user))
    return await _task_call(service.rename(task_id, principal.user, payload.name))


@router.delete("/{task_id}", response_model=TaskView)
async def delete_task(
    task_id: str,
    principal: Principal = Depends(current_principal),
    service: TaskService = Depends(task_service),
):
    return await _task_call(service.soft_delete(task_id, principal.user))


@router.post("/{task_id}/preflight", response_model=PreflightResponse)
async def preflight(
    task_id: str,
    principal: Principal = Depends(current_principal),
    service: TaskService = Depends(task_service),
):
    try:
        task, checks = await service.preflight(task_id, principal.user)
    except TaskError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return PreflightResponse(
        task=TaskView.model_validate(task),
        checks=checks,
        ready=all(check.ok for check in checks),
    )


@router.post("/{task_id}/audio-test/start")
async def start_audio_test(
    task_id: str,
    request: Request,
    principal: Principal = Depends(current_principal),
    service: TaskService = Depends(task_service),
):
    await _task_call(service.get_for(task_id, principal.user))
    hub = request.app.state.agent_hub
    connection = hub.get(principal.user.id)
    if connection is None:
        raise HTTPException(status_code=409, detail="桌面 Agent 未连接")
    capabilities = connection.device.get("capabilities") or []
    if "preflight_audio_test_v1" not in capabilities:
        raise HTTPException(status_code=409, detail="电脑助手版本过旧，请重新下载并打开最新版")
    hub.start_audio_test(principal.user.id, task_id)
    try:
        await hub.send(
            principal.user.id,
            {"type": "preflight.audio_test.start", "task_id": task_id},
        )
    except AgentUnavailable as exc:
        hub.stop_audio_test(principal.user.id, task_id)
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"ok": True}


@router.get("/{task_id}/audio-test")
async def audio_test_state(
    task_id: str,
    request: Request,
    principal: Principal = Depends(current_principal),
    service: TaskService = Depends(task_service),
):
    await _task_call(service.get_for(task_id, principal.user))
    state = request.app.state.agent_hub.audio_test_state(principal.user.id, task_id)
    return {**state, "agent_connected": request.app.state.agent_hub.is_connected(principal.user.id)}


@router.post("/{task_id}/audio-test/stop")
async def stop_audio_test(
    task_id: str,
    request: Request,
    principal: Principal = Depends(current_principal),
    service: TaskService = Depends(task_service),
):
    await _task_call(service.get_for(task_id, principal.user))
    hub = request.app.state.agent_hub
    hub.stop_audio_test(principal.user.id, task_id)
    try:
        await hub.send(principal.user.id, {"type": "preflight.audio_test.stop", "task_id": task_id})
    except AgentUnavailable:
        pass
    return {"ok": True}


@router.get("/{task_id}/preflight")
async def latest_preflight(
    task_id: str,
    request: Request,
    principal: Principal = Depends(current_principal),
    service: TaskService = Depends(task_service),
    session: AsyncSession = Depends(get_db),
):
    await _task_call(service.get_for(task_id, principal.user))
    event = await session.scalar(
        select(TaskEvent)
        .where(TaskEvent.task_id == task_id)
        .where(TaskEvent.event_type == "preflight.completed")
        .order_by(desc(TaskEvent.created_at))
        .limit(1)
    )
    connection = request.app.state.agent_hub.get(principal.user.id)
    if connection is None:
        return {
            "ready": False,
            "checks": [
                {
                    "key": "agent",
                    "label": "桌面 Agent",
                    "ok": False,
                    "detail": "桌面 Agent 未连接",
                    "latency_ms": None,
                }
            ],
        }
    if event is None or event.created_at.timestamp() < connection.connected_at:
        return {
            "ready": False,
            "checks": [
                {
                    "key": "agent",
                    "label": "桌面 Agent",
                    "ok": True,
                    "detail": "控制通道已连接，请重新确认声音",
                    "latency_ms": None,
                }
            ],
        }
    return event.payload


@router.post("/{task_id}/start", response_model=TaskView)
async def start_task(
    task_id: str,
    principal: Principal = Depends(current_principal),
    service: TaskService = Depends(task_service),
):
    return await _task_call(service.start(task_id, principal.user))


@router.post("/{task_id}/pause", response_model=TaskView)
async def pause_task(
    task_id: str,
    principal: Principal = Depends(current_principal),
    service: TaskService = Depends(task_service),
):
    return await _task_call(service.pause(task_id, principal.user))


@router.post("/{task_id}/resume", response_model=TaskView)
async def resume_task(
    task_id: str,
    principal: Principal = Depends(current_principal),
    service: TaskService = Depends(task_service),
):
    return await _task_call(service.resume(task_id, principal.user))


@router.post("/{task_id}/end", response_model=TaskView)
async def end_task(
    task_id: str,
    principal: Principal = Depends(current_principal),
    service: TaskService = Depends(task_service),
):
    return await _task_call(service.end(task_id, principal.user))


@router.post("/{task_id}/pairing")
async def create_pairing(
    task_id: str,
    request: Request,
    principal: Principal = Depends(current_principal),
    service: TaskService = Depends(task_service),
):
    task = await _task_call(service.get_for(task_id, principal.user))
    pairing = request.app.state.mobile_hub.issue(task.id, principal.user.id)
    return {
        "token": pairing.token,
        "expires_at": pairing.expires_at,
        "url": f"{request.app.state.settings.public_base_url}/m/pair/{pairing.token}",
        "connected": request.app.state.mobile_hub.is_connected(task.id),
    }


@router.get("/{task_id}/events", response_model=list[TaskEventView])
async def task_events(
    task_id: str,
    limit: int = Query(default=500, ge=1, le=5_000),
    types: str | None = Query(default=None),
    principal: Principal = Depends(current_principal),
    service: TaskService = Depends(task_service),
    session: AsyncSession = Depends(get_db),
):
    await _task_call(service.get_for(task_id, principal.user))
    statement = select(TaskEvent).where(TaskEvent.task_id == task_id)
    if types:
        requested_types = tuple(
            dict.fromkeys(value.strip() for value in types.split(",") if value.strip())
        )
        if requested_types:
            statement = statement.where(TaskEvent.event_type.in_(requested_types[:20]))
    rows = (
        await session.scalars(
            statement.order_by(desc(TaskEvent.created_at)).limit(limit)
        )
    ).all()
    return [
        TaskEventView(
            id=row.id,
            event_id=row.event_id,
            event_type=row.event_type,
            conversation_revision=row.conversation_revision,
            payload=row.payload,
            created_at=row.created_at,
        )
        for row in reversed(rows)
    ]


async def _task_call(awaitable):
    try:
        return await awaitable
    except TaskError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except AgentUnavailable as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
