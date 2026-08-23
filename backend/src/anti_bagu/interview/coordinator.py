from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import Awaitable, Callable

from anti_bagu.interview.context import FocusPromptBuilder, FocusPromptBuildResult
from anti_bagu.interview.conversation import ConversationStore
from anti_bagu.interview.events import (
    AnswerResult,
    Channel,
    FocusSource,
    RealtimeEvent,
    TranscriptEvent,
    TranscriptPhase,
    WaitResult,
)
from anti_bagu.interview.sink import EventSink
from anti_bagu.interview.state import SessionState
from anti_bagu.llm.base import FocusResponder, ScreenshotAnalyzer

ScreenshotStatusHandler = Callable[[dict[str, object]], Awaitable[None]]


class InterviewCoordinator:
    def __init__(
        self,
        focus_responder: FocusResponder,
        screenshot_analyzer: ScreenshotAnalyzer,
        sink: EventSink,
        prompt_builder: FocusPromptBuilder,
        *,
        session_id: str | None = None,
        debounce_seconds: float = 0.3,
        max_coalesce_seconds: float = 1.2,
        focus_timeout_seconds: float = 5.0,
        screenshot_timeout_seconds: float = 60.0,
    ) -> None:
        self.session_id = session_id or str(uuid.uuid4())
        self.store = ConversationStore()
        self.state = SessionState.LISTENING
        self._focus_responder = focus_responder
        self._screenshot_analyzer = screenshot_analyzer
        self._sink = sink
        self._prompt_builder = prompt_builder
        self._debounce_seconds = debounce_seconds
        self._max_coalesce_seconds = max_coalesce_seconds
        self._focus_timeout_seconds = focus_timeout_seconds
        self._screenshot_timeout_seconds = screenshot_timeout_seconds

        self._seen_final_events: set[str] = set()
        self._debounce_task: asyncio.Task[None] | None = None
        self._focus_task: asyncio.Task[None] | None = None
        self._screenshot_task: asyncio.Task[None] | None = None
        self._focus_generation = 0
        self._last_started_turn_id = 0
        self._coalesce_started_at: float | None = None
        self._last_interviewer_activity_at: float | None = None
        self._last_interviewer_audio_end: float | None = None
        self._screenshot_focus_active = False
        self._pending_voice_focus = False
        self._closing = False

    @property
    def model_task_active(self) -> bool:
        return self._task_active(self._focus_task) or self._task_active(
            self._screenshot_task
        )

    @property
    def screenshot_focus_active(self) -> bool:
        return self._screenshot_focus_active

    @property
    def active_focus_generation(self) -> int:
        return self._focus_generation

    async def handle_transcript(self, event: TranscriptEvent) -> None:
        await self._emit(
            f"transcript.{event.phase.value}", self._transcript_payload(event)
        )
        if event.phase is TranscriptPhase.PARTIAL:
            await self._handle_partial(event)
            return

        if event.event_id in self._seen_final_events:
            await self._emit(
                "transcript.duplicate",
                {
                    "channel": event.channel.value,
                    "event_id": event.event_id,
                    "utterance_id": event.utterance_id,
                },
            )
            return
        self._seen_final_events.add(event.event_id)
        turn = self.store.append_final(event)
        await self._emit(
            "transcript.committed",
            {
                "turn_id": turn.turn_id,
                "channel": turn.channel.value,
                "text": turn.text,
                "source_event_id": turn.event_id,
            },
        )

        if event.channel is Channel.CANDIDATE:
            return

        self._last_interviewer_audio_end = event.audio_ended_at
        if event.audio_ended_at is not None:
            await self._emit(
                "latency.updated",
                {"asr": max(0.0, (event.created_at - event.audio_ended_at) * 1000)},
            )
        self._mark_interviewer_activity()
        if self._screenshot_focus_active:
            self._pending_voice_focus = True
            await self._emit(
                "focus.blocked",
                {
                    "reason": "screenshot_focus_active",
                    "latest_turn_id": self.store.latest_turn_id,
                },
            )
            return
        await self._schedule_focus_window()

    async def handle_screenshot(
        self,
        *,
        screenshot_id: str,
        image_data: bytes,
        mime_type: str,
        storage_path: str,
        status_handler: ScreenshotStatusHandler | None = None,
    ) -> bool:
        if self._screenshot_focus_active:
            await self._emit(
                "screenshot.rejected",
                {"screenshot_id": screenshot_id, "reason": "focus_busy"},
            )
            return False

        self._screenshot_focus_active = True
        self._pending_voice_focus = False
        await self._cancel_task(self._debounce_task)
        self._debounce_task = None
        self._coalesce_started_at = None
        self._last_interviewer_activity_at = None
        await self._cancel_active_focus("screenshot_focus")

        prompt = self._prompt_builder.build(
            turns=self.store.turns,
            focuses=self.store.focuses,
        )
        self._focus_generation += 1
        generation = self._focus_generation
        self._last_started_turn_id = max(
            self._last_started_turn_id, prompt.through_turn_id
        )
        self.state = SessionState.EVALUATING
        await self._emit(
            "screenshot.accepted",
            {
                "screenshot_id": screenshot_id,
                "generation": generation,
                "mime_type": mime_type,
                "bytes": len(image_data),
                "storage_path": storage_path,
                "through_turn_id": prompt.through_turn_id,
            },
        )
        await self._emit(
            "focus.started",
            {
                "generation": generation,
                "source": FocusSource.SCREENSHOT.value,
                "screenshot_id": screenshot_id,
                "through_turn_id": prompt.through_turn_id,
                "included_turn_count": len(prompt.included_turn_ids),
                "included_focus_count": len(prompt.included_focus_ids),
                "estimated_prompt_tokens": prompt.estimated_total_tokens,
                "exclusive": True,
            },
        )
        await self._emit(
            "internal.llm.request",
            {
                "operation": "screenshot_focus",
                "generation": generation,
                "screenshot_id": screenshot_id,
                "storage_path": storage_path,
                "prompt": prompt.markdown,
                "estimated_prompt_tokens": prompt.estimated_total_tokens,
            },
        )
        self._screenshot_task = asyncio.create_task(
            self._run_screenshot_focus(
                generation=generation,
                screenshot_id=screenshot_id,
                image_data=image_data,
                mime_type=mime_type,
                prompt=prompt,
                status_handler=status_handler,
            )
        )
        return True

    @staticmethod
    def _transcript_payload(event: TranscriptEvent) -> dict[str, object]:
        return {
            "channel": event.channel.value,
            "text": event.text,
            "source_event_id": event.event_id,
            "utterance_id": event.utterance_id,
            "audio_started_at": event.audio_started_at,
            "audio_ended_at": event.audio_ended_at,
            "received_at": event.created_at,
        }

    async def wait_idle(self) -> None:
        while True:
            tasks = [
                task
                for task in (
                    self._debounce_task,
                    self._focus_task,
                    self._screenshot_task,
                )
                if self._task_active(task)
            ]
            if not tasks:
                return
            await asyncio.gather(*tasks, return_exceptions=True)
            await asyncio.sleep(0)

    async def close(self) -> None:
        self._closing = True
        await self._cancel_task(self._debounce_task)
        await self._cancel_task(self._focus_task)
        await self._cancel_task(self._screenshot_task)
        self._screenshot_task = None
        self._screenshot_focus_active = False

    async def _handle_partial(self, event: TranscriptEvent) -> None:
        if event.channel is not Channel.INTERVIEWER or not event.text.strip():
            return
        if self._task_active(self._debounce_task):
            self._mark_interviewer_activity()
            await self._schedule_focus_window()

    def _mark_interviewer_activity(self) -> None:
        now = time.monotonic()
        if self._coalesce_started_at is None:
            self._coalesce_started_at = now
        self._last_interviewer_activity_at = now

    async def _schedule_focus_window(self) -> None:
        if self._screenshot_focus_active:
            self._pending_voice_focus = True
            return
        is_reset = self._task_active(self._debounce_task)
        if is_reset:
            self._debounce_task.cancel()
        now = time.monotonic()
        coalesce_started = self._coalesce_started_at or now
        last_activity = self._last_interviewer_activity_at or now
        quiet_due = last_activity + self._debounce_seconds
        maximum_due = coalesce_started + self._max_coalesce_seconds
        delay = max(0.0, min(quiet_due, maximum_due) - now)
        await self._emit(
            "focus.window.reset" if is_reset else "focus.window.started",
            {
                "delay_ms": delay * 1000,
                "latest_turn_id": self.store.latest_turn_id,
                "quiet_window_ms": self._debounce_seconds * 1000,
                "maximum_window_ms": self._max_coalesce_seconds * 1000,
            },
        )
        self._debounce_task = asyncio.create_task(self._wait_and_start_focus(delay))

    async def _wait_and_start_focus(self, delay: float) -> None:
        current_task = asyncio.current_task()
        try:
            await asyncio.sleep(delay)
            self._coalesce_started_at = None
            self._last_interviewer_activity_at = None
            await self._emit(
                "focus.window.fired",
                {"latest_turn_id": self.store.latest_turn_id},
            )
            await self._start_focus_attempt()
        except asyncio.CancelledError:
            raise
        finally:
            if self._debounce_task is current_task:
                self._debounce_task = None

    async def _start_focus_attempt(self) -> None:
        if self._screenshot_focus_active:
            self._pending_voice_focus = True
            await self._emit(
                "focus.blocked",
                {
                    "reason": "screenshot_focus_active",
                    "latest_turn_id": self.store.latest_turn_id,
                },
            )
            return
        if self.store.latest_turn_id <= self._last_started_turn_id:
            await self._emit(
                "focus.skipped",
                {
                    "reason": "no_new_final_turn",
                    "latest_turn_id": self.store.latest_turn_id,
                    "last_started_turn_id": self._last_started_turn_id,
                },
            )
            return

        old_focus_task = self._focus_task
        if self._task_active(old_focus_task):
            cancelled_generation = self._focus_generation
            old_focus_task.cancel()
            await asyncio.gather(old_focus_task, return_exceptions=True)
            await self._emit(
                "focus.cancelled",
                {
                    "generation": cancelled_generation,
                    "reason": "superseded",
                    "superseded_through_turn_id": self.store.latest_turn_id,
                },
            )

        prompt = self._prompt_builder.build(
            turns=self.store.turns,
            focuses=self.store.focuses,
        )
        self._focus_generation += 1
        generation = self._focus_generation
        self._last_started_turn_id = prompt.through_turn_id
        self.state = SessionState.EVALUATING
        await self._emit(
            "focus.started",
            {
                "generation": generation,
                "dialogue_start_turn_id": prompt.dialogue_start_turn_id,
                "through_turn_id": prompt.through_turn_id,
                "included_turn_count": len(prompt.included_turn_ids),
                "included_focus_count": len(prompt.included_focus_ids),
                "removed_noise_turns": prompt.removed_noise_turns,
                "estimated_prompt_tokens": prompt.estimated_total_tokens,
                "compacted": prompt.compacted,
            },
        )
        await self._emit(
            "internal.llm.request",
            {
                "operation": "focus",
                "generation": generation,
                "prompt": prompt.markdown,
                "estimated_prompt_tokens": prompt.estimated_total_tokens,
            },
        )
        self._focus_task = asyncio.create_task(
            self._run_focus_attempt(generation, prompt)
        )

    async def _run_focus_attempt(
        self,
        generation: int,
        prompt: FocusPromptBuildResult,
    ) -> None:
        model_started_at = time.time()
        try:
            result = await asyncio.wait_for(
                self._focus_responder.respond(prompt=prompt.markdown),
                timeout=self._focus_timeout_seconds,
            )
            duration_ms = max(0.0, (time.time() - model_started_at) * 1000)
            if generation != self._focus_generation:
                await self._emit(
                    "focus.discarded",
                    {
                        "generation": generation,
                        "active_generation": self._focus_generation,
                        "reason": "stale_generation",
                        "duration_ms": duration_ms,
                    },
                )
                return

            await self._emit(
                "focus.responded",
                {
                    "generation": generation,
                    "through_turn_id": prompt.through_turn_id,
                    "result_type": result.type,
                    "question": result.question if isinstance(result, AnswerResult) else "",
                    "duration_ms": duration_ms,
                },
            )
            await self._emit(
                "internal.llm.response",
                {
                    "operation": "focus",
                    "generation": generation,
                    "result": result.model_dump(mode="json"),
                    "duration_ms": duration_ms,
                },
            )

            if isinstance(result, WaitResult):
                self.state = SessionState.LISTENING
                await self._emit(
                    "focus.wait",
                    {
                        "generation": generation,
                        "through_turn_id": prompt.through_turn_id,
                        "duration_ms": duration_ms,
                    },
                )
                return

            committed = self.store.commit_focus(
                question=result.question,
                recommended_answer=result.answer,
                source_end_turn_id=prompt.through_turn_id,
                code=result.code,
            )
            await self._emit(
                "focus.updated",
                {
                    "protocol_version": 2,
                    "focus_id": committed.focus_id,
                    "generation": generation,
                    "question": committed.question,
                    "source": committed.source.value,
                    "has_code": bool(committed.code),
                    "source_start_turn_id": committed.source_start_turn_id,
                    "source_end_turn_id": committed.source_end_turn_id,
                },
            )
            self.state = SessionState.ANSWERING
            await self._emit_model_latency(model_started_at)
            await self._emit(
                "answer.completed",
                {
                    "protocol_version": 2,
                    "focus_id": committed.focus_id,
                    "question": committed.question,
                    "answer": committed.recommended_answer,
                    "code": committed.code,
                    "source": committed.source.value,
                    "duration_ms": duration_ms,
                },
            )
            self.state = SessionState.LISTENING
        except asyncio.CancelledError:
            raise
        except TimeoutError:
            if generation == self._focus_generation:
                self.state = SessionState.LISTENING
                await self._emit(
                    "focus.timeout",
                    {
                        "generation": generation,
                        "through_turn_id": prompt.through_turn_id,
                        "timeout_ms": self._focus_timeout_seconds * 1000,
                    },
                )
                await self._emit(
                    "error",
                    {"message": "Focus request timed out", "operation": "focus"},
                )
        except Exception as exc:
            if generation == self._focus_generation:
                self.state = SessionState.LISTENING
                await self._emit(
                    "focus.error",
                    {
                        "generation": generation,
                        "through_turn_id": prompt.through_turn_id,
                        "error_type": type(exc).__name__,
                        "message": str(exc),
                    },
                )
                await self._emit(
                    "error",
                    {"message": str(exc), "operation": "focus"},
                )

    async def _run_screenshot_focus(
        self,
        *,
        generation: int,
        screenshot_id: str,
        image_data: bytes,
        mime_type: str,
        prompt: FocusPromptBuildResult,
        status_handler: ScreenshotStatusHandler | None,
    ) -> None:
        current_task = asyncio.current_task()
        model_started_at = time.time()
        outcome = "completed"
        try:
            result = await asyncio.wait_for(
                self._screenshot_analyzer.analyze(
                    prompt=prompt.markdown,
                    image_data=image_data,
                    mime_type=mime_type,
                ),
                timeout=self._screenshot_timeout_seconds,
            )
            duration_ms = max(0.0, (time.time() - model_started_at) * 1000)
            await self._emit(
                "focus.responded",
                {
                    "generation": generation,
                    "through_turn_id": prompt.through_turn_id,
                    "result_type": result.type,
                    "source": FocusSource.SCREENSHOT.value,
                    "screenshot_id": screenshot_id,
                    "question": result.question if isinstance(result, AnswerResult) else "",
                    "duration_ms": duration_ms,
                },
            )
            await self._emit(
                "internal.llm.response",
                {
                    "operation": "screenshot_focus",
                    "generation": generation,
                    "screenshot_id": screenshot_id,
                    "result": result.model_dump(mode="json"),
                    "duration_ms": duration_ms,
                },
            )
            if isinstance(result, WaitResult):
                outcome = "no_question"
                await self._emit(
                    "focus.wait",
                    {
                        "generation": generation,
                        "through_turn_id": prompt.through_turn_id,
                        "source": FocusSource.SCREENSHOT.value,
                        "screenshot_id": screenshot_id,
                        "duration_ms": duration_ms,
                    },
                )
                return

            committed = self.store.commit_focus(
                question=result.question,
                recommended_answer=result.answer,
                source_end_turn_id=prompt.through_turn_id,
                code=result.code,
                source=FocusSource.SCREENSHOT,
                screenshot_id=screenshot_id,
            )
            await self._emit(
                "focus.updated",
                {
                    "protocol_version": 2,
                    "focus_id": committed.focus_id,
                    "generation": generation,
                    "question": committed.question,
                    "source": committed.source.value,
                    "screenshot_id": screenshot_id,
                    "has_code": bool(committed.code),
                    "source_start_turn_id": committed.source_start_turn_id,
                    "source_end_turn_id": committed.source_end_turn_id,
                },
            )
            await self._emit_model_latency(model_started_at)
            await self._emit(
                "answer.completed",
                {
                    "protocol_version": 2,
                    "focus_id": committed.focus_id,
                    "question": committed.question,
                    "answer": committed.recommended_answer,
                    "code": committed.code,
                    "source": committed.source.value,
                    "screenshot_id": screenshot_id,
                    "duration_ms": duration_ms,
                },
            )
        except asyncio.CancelledError:
            outcome = "cancelled"
            raise
        except TimeoutError:
            outcome = "timeout"
            await self._emit(
                "focus.timeout",
                {
                    "generation": generation,
                    "source": FocusSource.SCREENSHOT.value,
                    "screenshot_id": screenshot_id,
                    "timeout_ms": self._screenshot_timeout_seconds * 1000,
                },
            )
            await self._emit(
                "error",
                {"message": "截图分析超时，请重新截图", "operation": "screenshot_focus"},
            )
        except Exception as exc:
            outcome = "error"
            await self._emit(
                "focus.error",
                {
                    "generation": generation,
                    "source": FocusSource.SCREENSHOT.value,
                    "screenshot_id": screenshot_id,
                    "error_type": type(exc).__name__,
                    "message": str(exc),
                },
            )
            await self._emit(
                "error", {"message": str(exc), "operation": "screenshot_focus"}
            )
        finally:
            duration_ms = max(0.0, (time.time() - model_started_at) * 1000)
            self.state = SessionState.LISTENING
            self._screenshot_focus_active = False
            if self._screenshot_task is current_task:
                self._screenshot_task = None
            await self._emit(
                "screenshot.focus.released",
                {
                    "screenshot_id": screenshot_id,
                    "generation": generation,
                    "outcome": outcome,
                    "duration_ms": duration_ms,
                    "pending_voice_focus": self._pending_voice_focus,
                },
            )
            if status_handler is not None:
                try:
                    await status_handler(
                        {
                            "type": "screenshot.status",
                            "screenshot_id": screenshot_id,
                            "status": outcome,
                            "duration_ms": duration_ms,
                        }
                    )
                except Exception:
                    pass
            should_refresh = (
                self._pending_voice_focus
                and self.store.latest_turn_id > self._last_started_turn_id
                and not self._closing
            )
            self._pending_voice_focus = False
            if should_refresh:
                self._mark_interviewer_activity()
                await self._schedule_focus_window()

    async def _cancel_active_focus(self, reason: str) -> bool:
        if not self._task_active(self._focus_task):
            return False
        cancelled_generation = self._focus_generation
        self._focus_task.cancel()
        await asyncio.gather(self._focus_task, return_exceptions=True)
        self._focus_task = None
        await self._emit(
            "focus.cancelled",
            {"generation": cancelled_generation, "reason": reason},
        )
        return True

    async def _emit_model_latency(self, model_started_at: float) -> None:
        now = time.time()
        payload: dict[str, object] = {
            "model": max(0.0, (now - model_started_at) * 1000)
        }
        if self._last_interviewer_audio_end is not None:
            payload["endToEnd"] = max(
                0.0, (now - self._last_interviewer_audio_end) * 1000
            )
        await self._emit("latency.updated", payload)

    async def _emit(self, event_type: str, payload: dict[str, object]) -> None:
        await self._sink.publish(
            RealtimeEvent(
                type=event_type,
                session_id=self.session_id,
                conversation_revision=self.store.revision,
                payload=payload,
            )
        )

    @staticmethod
    def _task_active(task: asyncio.Task[None] | None) -> bool:
        return task is not None and not task.done()

    @staticmethod
    async def _cancel_task(task: asyncio.Task[None] | None) -> None:
        if task is None or task.done():
            return
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
