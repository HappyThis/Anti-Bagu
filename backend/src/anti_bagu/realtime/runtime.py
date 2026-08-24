from __future__ import annotations

import asyncio

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from anti_bagu.api.event_hub import EventHub
from anti_bagu.config import Settings
from anti_bagu.interview.context import FocusPromptBuilder, TokenEstimator
from anti_bagu.interview.coordinator import InterviewCoordinator
from anti_bagu.llm.deepseek import (
    DeepSeekInterviewResponder,
    UnavailableInterviewResponder,
)
from anti_bagu.llm.prompts import INTERVIEW_SYSTEM_PROMPT
from anti_bagu.persistence.runtime_state import PersistedRuntimeState, load_runtime_state
from anti_bagu.persistence.task_events import TaskEventRecorder
from anti_bagu.telemetry.audit import DailyJsonlAudit


class TaskRuntime:
    def __init__(
        self,
        task_id: str,
        settings: Settings,
        event_hub: EventHub,
        recorder: TaskEventRecorder,
    ) -> None:
        self.task_id = task_id
        self.settings = settings
        self.event_hub = event_hub
        self.recorder = recorder
        self.dashscope_api_key: str | None = None
        self._responder = UnavailableInterviewResponder()
        self.coordinator = self._new_coordinator()

    @property
    def configured(self) -> bool:
        return bool(self.dashscope_api_key) and isinstance(
            self._responder, DeepSeekInterviewResponder
        )

    async def configure(self, *, dashscope_api_key: str, deepseek_api_key: str) -> None:
        turns = self.coordinator.store.turns
        focuses = self.coordinator.store.focuses
        last_analyzed_turn_id = self.coordinator.last_analyzed_turn_id
        await self.coordinator.close()
        await self._close_models()
        self.dashscope_api_key = dashscope_api_key
        self._responder = DeepSeekInterviewResponder(
            deepseek_api_key,
            self.settings.deepseek_base_url,
            self.settings.deepseek_model,
        )
        self.coordinator = self._new_coordinator()
        self.coordinator.restore_state(
            turns=turns,
            focuses=focuses,
            last_analyzed_turn_id=last_analyzed_turn_id,
        )

    def restore_state(self, state: PersistedRuntimeState) -> None:
        self.coordinator.restore_state(
            turns=state.turns,
            focuses=state.focuses,
            last_analyzed_turn_id=state.last_analyzed_turn_id,
        )

    async def close(self) -> None:
        await self.coordinator.close()
        await self._close_models()
        self.dashscope_api_key = None
        await self.recorder.close()

    def _new_coordinator(self) -> InterviewCoordinator:
        prompt_builder = FocusPromptBuilder(
            system_prompt=INTERVIEW_SYSTEM_PROMPT,
            target_tokens=self.settings.focus_prompt_target_tokens,
            dialogue_target_tokens=self.settings.focus_dialogue_target_tokens,
            history_target_tokens=self.settings.focus_history_target_tokens,
            estimator=TokenEstimator(self.settings.focus_characters_per_token),
        )
        return InterviewCoordinator(
            self._responder,
            self.event_hub,
            prompt_builder,
            session_id=self.task_id,
            debounce_seconds=self.settings.focus_debounce_ms / 1000,
            max_coalesce_seconds=self.settings.focus_max_coalesce_ms / 1000,
            focus_timeout_seconds=self.settings.focus_timeout_seconds,
            screenshot_timeout_seconds=self.settings.screenshot_focus_timeout_seconds,
        )

    async def _close_models(self) -> None:
        close = getattr(self._responder, "close", None)
        if close is not None:
            await close()


class RuntimeRegistry:
    def __init__(
        self,
        settings: Settings,
        session_factory: async_sessionmaker[AsyncSession],
        audit: DailyJsonlAudit,
    ) -> None:
        self._settings = settings
        self._sessions = session_factory
        self._audit = audit
        self._runtimes: dict[str, TaskRuntime] = {}
        self._lock = asyncio.Lock()

    async def get(self, task_id: str) -> TaskRuntime:
        runtime = self._runtimes.get(task_id)
        if runtime is not None:
            return runtime
        async with self._lock:
            runtime = self._runtimes.get(task_id)
            if runtime is not None:
                return runtime
            recorder = TaskEventRecorder(
                task_id,
                self._sessions,
                queue_size=self._settings.audit_queue_size,
            )
            await recorder.start()
            event_hub = EventHub(audit=self._audit, recorder=recorder.record)
            runtime = TaskRuntime(task_id, self._settings, event_hub, recorder)
            runtime.restore_state(await load_runtime_state(self._sessions, task_id))
            self._runtimes[task_id] = runtime
            return runtime

    async def close(self) -> None:
        runtimes = list(self._runtimes.values())
        self._runtimes.clear()
        await asyncio.gather(*(runtime.close() for runtime in runtimes))

    async def release(self, task_id: str) -> None:
        async with self._lock:
            runtime = self._runtimes.pop(task_id, None)
        if runtime is not None:
            await runtime.close()

    @property
    def active_count(self) -> int:
        return len(self._runtimes)
