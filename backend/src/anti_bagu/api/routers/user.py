from __future__ import annotations

import asyncio
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from anti_bagu.api.dependencies import (
    Principal,
    current_principal,
    get_db,
    get_model_credential_service,
)
from anti_bagu.api.schemas import DeviceView, ModelCredentialUpdateRequest
from anti_bagu.credentials.service import ModelCredentials, ModelCredentialService
from anti_bagu.persistence.audio_archive import wav_header
from anti_bagu.persistence.models import AgentDevice, Task, TaskEvent

router = APIRouter(prefix="/api/v1", tags=["user"])


@router.get("/tasks/{task_id}/audio/{channel}")
async def task_audio(
    task_id: str,
    channel: str,
    request: Request,
    principal: Principal = Depends(current_principal),
    session: AsyncSession = Depends(get_db),
):
    if channel not in {"interviewer", "candidate"}:
        raise HTTPException(status_code=404, detail="音频通道不存在")
    task = await session.get(Task, task_id)
    if (
        task is None
        or (task.deleted_at is not None and principal.user.role != "admin")
        or (principal.user.role != "admin" and task.owner_id != principal.user.id)
    ):
        raise HTTPException(status_code=404, detail="任务不存在")
    path = request.app.state.settings.storage_dir / "tasks" / task_id / "audio" / f"{channel}.pcm"
    if not path.exists():
        raise HTTPException(status_code=404, detail="该通道暂无音频")
    size = path.stat().st_size
    return StreamingResponse(
        _wav_stream(path),
        media_type="audio/wav",
        headers={
            "Content-Disposition": f'attachment; filename="{task_id}-{channel}.wav"',
            "Content-Length": str(size + 44),
        },
    )


def _wav_stream(path: Path) -> Iterator[bytes]:
    yield wav_header(pcm_bytes=path.stat().st_size)
    with path.open("rb") as handle:
        while chunk := handle.read(64 * 1024):
            yield chunk


@router.get("/reviews")
async def reviews(
    principal: Principal = Depends(current_principal),
    session: AsyncSession = Depends(get_db),
):
    tasks = (
        await session.scalars(
            select(Task)
            .where(Task.owner_id == principal.user.id)
            .where(Task.status == "completed")
            .where(Task.deleted_at.is_(None))
            .order_by(desc(Task.ended_at))
        )
    ).all()
    result = []
    for task in tasks:
        events = (
            await session.scalars(
                select(TaskEvent).where(TaskEvent.task_id == task.id)
            )
        ).all()
        latencies = [
            float(event.payload["endToEnd"])
            for event in events
            if event.event_type == "latency.updated"
            and event.payload.get("endToEnd") is not None
        ]
        duration_seconds = (
            max(0.0, (task.ended_at - task.started_at).total_seconds())
            if task.started_at is not None and task.ended_at is not None
            else 0.0
        )
        result.append(
            {
                "id": task.id,
                "task_id": task.id,
                "task_name": task.name,
                "date": task.started_at or task.created_at,
                "duration_seconds": duration_seconds,
                "question_count": sum(
                    event.event_type == "focus.updated" for event in events
                ),
                "avg_latency_ms": sum(latencies) / len(latencies) if latencies else 0,
            }
        )
    return result


@router.get("/devices", response_model=list[DeviceView])
async def devices(
    request: Request,
    principal: Principal = Depends(current_principal),
    session: AsyncSession = Depends(get_db),
):
    connection = request.app.state.agent_hub.get(principal.user.id)
    rows = (
        await session.scalars(
            select(AgentDevice)
            .where(AgentDevice.user_id == principal.user.id)
            .order_by(desc(AgentDevice.last_seen_at))
        )
    ).all()
    result: list[DeviceView] = []
    for row in rows:
        online = connection is not None and connection.device.get("device_key") == row.device_key
        result.append(
            DeviceView(
                id=row.id,
                name=row.name,
                platform=row.platform,
                agent_version=row.agent_version,
                status="online" if online else "offline",
                last_seen_at=(
                    datetime.fromtimestamp(connection.last_seen_at, UTC)
                    if online
                    else row.last_seen_at
                ),
                metadata=row.metadata_json,
            )
        )
    return result


@router.get("/model-status")
async def model_status(
    request: Request,
    principal: Principal = Depends(current_principal),
    credentials: ModelCredentialService = Depends(get_model_credential_service),
):
    connection = request.app.state.agent_hub.get(principal.user.id)
    configured = await credentials.configured(principal.user.id)
    return {
        "agent_connected": connection is not None,
        "asr": {
            "name": request.app.state.settings.asr_model,
            "configured": configured,
        },
        "llm": {
            "name": request.app.state.settings.deepseek_model,
            "configured": configured,
        },
        "storage": "服务器加密保存",
    }


@router.put("/model-credentials")
async def update_model_credentials(
    payload: ModelCredentialUpdateRequest,
    request: Request,
    principal: Principal = Depends(current_principal),
    credentials: ModelCredentialService = Depends(get_model_credential_service),
):
    existing = await credentials.get(principal.user.id)
    dashscope_key = (
        payload.dashscope_api_key.strip()
        if payload.dashscope_api_key is not None
        else existing.dashscope_api_key if existing else ""
    )
    deepseek_key = (
        payload.deepseek_api_key.strip()
        if payload.deepseek_api_key is not None
        else existing.deepseek_api_key if existing else ""
    )
    if not dashscope_key or not deepseek_key:
        raise HTTPException(status_code=400, detail="请完整填写两项服务密钥")

    asr_result, llm_result = await asyncio.gather(
        request.app.state.model_verifier.verify_asr(dashscope_key),
        request.app.state.model_verifier.verify_llm(deepseek_key),
    )
    failures = [result.detail for result in (asr_result, llm_result) if not result.ok]
    if failures:
        raise HTTPException(status_code=400, detail="；".join(failures))

    await credentials.save(
        principal.user.id,
        ModelCredentials(
            dashscope_api_key=dashscope_key,
            deepseek_api_key=deepseek_key,
        ),
    )
    return {
        "saved": True,
        "asr": {
            "name": request.app.state.settings.asr_model,
            "configured": True,
            "latency_ms": asr_result.latency_ms,
        },
        "llm": {
            "name": request.app.state.settings.deepseek_model,
            "configured": True,
            "latency_ms": llm_result.latency_ms,
        },
        "storage": "服务器加密保存",
    }
