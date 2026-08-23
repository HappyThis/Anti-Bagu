from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from anti_bagu.agent.hub import AgentHub, AgentUnavailable
from anti_bagu.api.schemas import PreflightCheck
from anti_bagu.config import Settings
from anti_bagu.credentials.service import ModelCredentialService
from anti_bagu.interview.events import RealtimeEvent
from anti_bagu.mobile.hub import MobileHub
from anti_bagu.persistence.models import PlatformAudit, Task, User
from anti_bagu.realtime.runtime import RuntimeRegistry
from anti_bagu.tasks.model_verifier import ModelVerifier


class TaskError(ValueError):
    pass


class TaskService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        settings: Settings,
        agents: AgentHub,
        mobiles: MobileHub,
        runtimes: RuntimeRegistry,
        verifier: ModelVerifier,
        credentials: ModelCredentialService,
    ) -> None:
        self._sessions = session_factory
        self._settings = settings
        self._agents = agents
        self._mobiles = mobiles
        self._runtimes = runtimes
        self._verifier = verifier
        self._credentials = credentials

    async def list_for(self, user: User) -> list[Task]:
        async with self._sessions() as session:
            statement = (
                select(Task)
                .where(Task.deleted_at.is_(None))
                .order_by(desc(Task.created_at))
            )
            if user.role != "admin":
                statement = statement.where(Task.owner_id == user.id)
            return list((await session.scalars(statement)).all())

    async def get_for(self, task_id: str, user: User) -> Task:
        async with self._sessions() as session:
            task = await session.get(Task, task_id)
            if (
                task is None
                or task.deleted_at is not None
                or (user.role != "admin" and task.owner_id != user.id)
            ):
                raise TaskError("任务不存在")
            return task

    async def create(
        self,
        user: User,
        *,
        name: str,
        mode: str,
        mobile_required: bool,
    ) -> Task:
        task = Task(
            owner_id=user.id,
            name=name.strip(),
            mode=mode,
            mobile_required=mobile_required,
            status="draft",
        )
        async with self._sessions() as session:
            session.add(task)
            await session.flush()
            session.add(
                PlatformAudit(
                    actor_user_id=user.id,
                    action="task.created",
                    target_type="task",
                    target_id=task.id,
                )
            )
            await session.commit()
            await session.refresh(task)
        await self._runtimes.get(task.id)
        return task

    async def rename(self, task_id: str, user: User, name: str) -> Task:
        async with self._sessions() as session:
            task = await self._owned_task(session, task_id, user)
            task.name = name.strip()
            await session.commit()
            await session.refresh(task)
        return task

    async def soft_delete(self, task_id: str, user: User) -> Task:
        async with self._sessions() as session:
            task = await self._owned_task(session, task_id, user)
            if task.status in {"running", "paused"}:
                raise TaskError("进行中的面试不能删除，请先结束面试")
            task.deleted_at = datetime.now(UTC)
            task.deleted_by_id = user.id
            session.add(
                PlatformAudit(
                    actor_user_id=user.id,
                    action="task.deleted",
                    target_type="task",
                    target_id=task.id,
                )
            )
            await session.commit()
            await session.refresh(task)
        await self._runtimes.release(task_id)
        return task

    async def preflight(self, task_id: str, user: User) -> tuple[Task, list[PreflightCheck]]:
        await self._set_status(task_id, user, "checking")
        checks: list[PreflightCheck] = []
        if not self._agents.is_connected(user.id):
            checks.append(
                PreflightCheck(
                    key="agent",
                    label="桌面 Agent",
                    ok=False,
                    detail="桌面 Agent 未连接",
                )
            )
            task = await self._set_status(task_id, user, "check_failed")
            await self._record_preflight(task_id, checks)
            return task, checks

        checks.append(
            PreflightCheck(
                key="agent", label="桌面 Agent", ok=True, detail="控制通道已连接"
            )
        )
        try:
            result = await self._agents.request_preflight(user.id, task_id)
        except AgentUnavailable as exc:
            checks.append(
                PreflightCheck(
                    key="agent_response",
                    label="Agent 响应",
                    ok=False,
                    detail=str(exc),
                )
            )
            task = await self._set_status(task_id, user, "check_failed")
            await self._record_preflight(task_id, checks)
            return task, checks

        permissions = result.get("permissions") or {}
        audio_processing = result.get("audio_processing") or {}
        screen_ok = bool(permissions.get("screen_capture"))
        mic_ok = bool(permissions.get("microphone"))
        aec3_ok = bool(audio_processing.get("aec3"))
        checks.extend(
            (
                PreflightCheck(
                    key="system_audio",
                    label="系统音频",
                    ok=screen_ok,
                    detail="权限正常" if screen_ok else "缺少屏幕与系统音频录制权限",
                ),
                PreflightCheck(
                    key="microphone",
                    label="麦克风",
                    ok=mic_ok,
                    detail="权限正常" if mic_ok else "缺少麦克风权限",
                ),
                PreflightCheck(
                    key="aec3",
                    label="回声消除",
                    ok=aec3_ok,
                    detail="AEC3 已就绪" if aec3_ok else "电脑助手缺少 AEC3 组件，请重新下载",
                ),
            )
        )
        credentials = await self._credentials.get(user.id)
        dashscope_key = credentials.dashscope_api_key if credentials else ""
        deepseek_key = credentials.deepseek_api_key if credentials else ""

        if dashscope_key and deepseek_key:
            asr_verified, llm_verified = await asyncio.gather(
                self._verifier.verify_asr(dashscope_key),
                self._verifier.verify_llm(deepseek_key),
            )
            checks.append(
                PreflightCheck(
                    key="asr",
                    label="ASR 模型",
                    ok=asr_verified.ok,
                    detail=asr_verified.detail,
                    latency_ms=asr_verified.latency_ms,
                )
            )
            checks.append(
                PreflightCheck(
                    key="llm",
                    label="LLM 模型",
                    ok=llm_verified.ok,
                    detail=llm_verified.detail,
                    latency_ms=llm_verified.latency_ms,
                )
            )
        else:
            checks.extend(
                (
                    PreflightCheck(
                        key="asr",
                        label="ASR 模型",
                        ok=False,
                        detail="请先在网页设置中保存语音识别服务密钥",
                    ),
                    PreflightCheck(
                        key="llm",
                        label="LLM 模型",
                        ok=False,
                        detail="请先在网页设置中保存回答服务密钥",
                    ),
                )
            )

        task = await self.get_for(task_id, user)
        mobile_ok = not task.mobile_required or self._mobiles.is_connected(task_id)
        checks.append(
            PreflightCheck(
                key="mobile",
                label="手机端",
                ok=mobile_ok,
                detail="已连接" if mobile_ok else "请先扫码连接手机端",
            )
        )
        ready = all(check.ok for check in checks)
        if ready:
            runtime = await self._runtimes.get(task_id)
            await runtime.configure(
                dashscope_api_key=dashscope_key, deepseek_api_key=deepseek_key
            )
        task = await self._set_status(task_id, user, "ready" if ready else "check_failed")
        await self._record_preflight(task_id, checks)
        return task, checks

    async def start(self, task_id: str, user: User) -> Task:
        task = await self.get_for(task_id, user)
        if task.status != "ready":
            raise TaskError("任务必须先通过系统检查")
        if not self._agents.is_connected(user.id):
            raise AgentUnavailable("桌面 Agent 未连接")
        credentials = await self._credentials.get(user.id)
        if (
            credentials is None
            or not credentials.dashscope_api_key
            or not credentials.deepseek_api_key
        ):
            raise TaskError("请先在设置中保存模型服务密钥")
        runtime = await self._runtimes.get(task_id)
        await runtime.configure(
            dashscope_api_key=credentials.dashscope_api_key,
            deepseek_api_key=credentials.deepseek_api_key,
        )
        self._agents.stop_audio_test(user.id, task_id)
        await self._agents.send(user.id, {"type": "task.start", "task_id": task_id})
        return await self._set_status(task_id, user, "running", mark_started=True)

    async def pause(self, task_id: str, user: User) -> Task:
        await self._agents.send(user.id, {"type": "task.pause", "task_id": task_id})
        return await self._set_status(task_id, user, "paused")

    async def resume(self, task_id: str, user: User) -> Task:
        await self._agents.send(user.id, {"type": "task.resume", "task_id": task_id})
        return await self._set_status(task_id, user, "running")

    async def end(self, task_id: str, user: User) -> Task:
        try:
            await self._agents.send(user.id, {"type": "task.end", "task_id": task_id})
        except AgentUnavailable:
            pass
        self._mobiles.revoke(task_id)
        task = await self._set_status(task_id, user, "completed", mark_ended=True)
        await self._runtimes.release(task_id)
        return task

    async def _set_status(
        self,
        task_id: str,
        user: User,
        status: str,
        *,
        mark_started: bool = False,
        mark_ended: bool = False,
    ) -> Task:
        async with self._sessions() as session:
            task = await self._owned_task(session, task_id, user)
            task.status = status
            now = datetime.now(UTC)
            if mark_started and task.started_at is None:
                task.started_at = now
            if mark_ended:
                task.ended_at = now
            session.add(
                PlatformAudit(
                    actor_user_id=user.id,
                    action=f"task.{status}",
                    target_type="task",
                    target_id=task.id,
                )
            )
            await session.commit()
            await session.refresh(task)
        runtime = await self._runtimes.get(task_id)
        await runtime.event_hub.publish(
            RealtimeEvent(
                type="task.status",
                session_id=task_id,
                conversation_revision=runtime.coordinator.store.revision,
                payload={"status": status},
            )
        )
        return task

    async def _record_preflight(
        self, task_id: str, checks: list[PreflightCheck]
    ) -> None:
        runtime = await self._runtimes.get(task_id)
        await runtime.event_hub.publish(
            RealtimeEvent(
                type="preflight.completed",
                session_id=task_id,
                conversation_revision=runtime.coordinator.store.revision,
                payload={
                    "ready": all(check.ok for check in checks),
                    "checks": [check.model_dump(mode="json") for check in checks],
                },
            )
        )

    @staticmethod
    async def _owned_task(session: AsyncSession, task_id: str, user: User) -> Task:
        task = await session.get(Task, task_id)
        if task is None or task.deleted_at is not None or task.owner_id != user.id:
            raise TaskError("任务不存在")
        return task
