from __future__ import annotations

import asyncio
import json
import time
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from websockets.asyncio.client import ClientConnection, connect

from anti_bagu.interview.events import (
    Channel,
    TranscriptEvent,
    TranscriptPhase,
)


TranscriptHandler = Callable[[TranscriptEvent], Awaitable[None]]


class QwenStreamingASRSession:
    def __init__(
        self,
        *,
        channel: Channel,
        api_key: str,
        ws_url: str,
        model: str,
        transcript_handler: TranscriptHandler,
        sample_rate: int = 16_000,
        frame_duration_ms: int = 100,
    ) -> None:
        self.channel = channel
        self._api_key = api_key
        self._ws_url = ws_url
        self._model = model
        self._transcript_handler = transcript_handler
        self._sample_rate = sample_rate
        self._frame_duration_seconds = frame_duration_ms / 1000
        self._task_id = uuid.uuid4().hex
        self._connection: ClientConnection | None = None
        self._receiver_task: asyncio.Task[None] | None = None
        self._started = asyncio.Event()
        self._finished = asyncio.Event()
        self._error: RuntimeError | None = None
        self._audio_origin: float | None = None
        self._utterance_index = 0
        self._active_utterance_id: str | None = None
        self._event_index = 0

    async def start(self) -> None:
        self._connection = await connect(
            self._ws_url,
            additional_headers={"Authorization": f"bearer {self._api_key}"},
            ping_interval=20,
            ping_timeout=20,
            max_size=4 * 1024 * 1024,
        )
        self._receiver_task = asyncio.create_task(self._receive_loop())
        await self._connection.send(json.dumps(self._run_task_message(), ensure_ascii=False))
        await asyncio.wait_for(self._started.wait(), timeout=10)
        if self._error is not None:
            raise self._error

    async def send_audio(self, pcm: bytes, *, captured_at: float) -> None:
        if self._error is not None:
            raise self._error
        if self._connection is None:
            raise RuntimeError("ASR session is not connected")
        if self._audio_origin is None:
            self._audio_origin = captured_at - self._frame_duration_seconds
        await self._connection.send(pcm)

    async def close(self) -> None:
        connection = self._connection
        receiver = self._receiver_task
        self._connection = None
        self._receiver_task = None
        if connection is not None:
            try:
                await connection.send(json.dumps(self._finish_task_message()))
                await asyncio.wait_for(self._finished.wait(), timeout=1.5)
            except Exception:
                pass
            await connection.close()
        if receiver is not None and not receiver.done():
            receiver.cancel()
            await asyncio.gather(receiver, return_exceptions=True)

    async def _receive_loop(self) -> None:
        assert self._connection is not None
        try:
            async for raw_message in self._connection:
                if isinstance(raw_message, bytes):
                    continue
                message = json.loads(raw_message)
                event_name = message.get("header", {}).get("event")
                if event_name == "task-started":
                    self._started.set()
                elif event_name == "result-generated":
                    await self._handle_result(message)
                elif event_name == "task-finished":
                    self._finished.set()
                    return
                elif event_name == "task-failed":
                    error_message = message.get("header", {}).get(
                        "error_message", "Qwen ASR task failed"
                    )
                    self._error = RuntimeError(str(error_message))
                    self._started.set()
                    self._finished.set()
                    return
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._error = RuntimeError(f"Qwen ASR connection failed: {exc}")
            self._started.set()
            self._finished.set()

    async def _handle_result(self, message: dict[str, Any]) -> None:
        sentence = (
            message.get("payload", {}).get("output", {}).get("sentence", {})
        )
        text = str(sentence.get("text") or "").strip()
        if not text:
            return

        if self._active_utterance_id is None:
            self._active_utterance_id = f"{self._task_id}-{self._utterance_index}"
        sentence_end = bool(sentence.get("sentence_end"))
        self._event_index += 1
        audio_origin = self._audio_origin
        begin_ms = sentence.get("begin_time")
        end_ms = self._latest_audio_end_ms(sentence)
        event = TranscriptEvent(
            event_id=f"{self._task_id}-{self._event_index}",
            channel=self.channel,
            phase=(
                TranscriptPhase.FINAL if sentence_end else TranscriptPhase.PARTIAL
            ),
            text=text,
            utterance_id=self._active_utterance_id,
            audio_started_at=(
                audio_origin + float(begin_ms) / 1000
                if audio_origin is not None and begin_ms is not None
                else None
            ),
            audio_ended_at=(
                audio_origin + end_ms / 1000
                if audio_origin is not None and end_ms is not None
                else None
            ),
            created_at=time.time(),
        )
        await self._transcript_handler(event)
        if sentence_end:
            self._active_utterance_id = None
            self._utterance_index += 1

    @staticmethod
    def _latest_audio_end_ms(sentence: dict[str, Any]) -> float | None:
        word_ends = [
            float(word["end_time"])
            for word in sentence.get("words") or []
            if word.get("end_time") is not None
        ]
        if word_ends:
            return max(word_ends)
        if sentence.get("end_time") is not None:
            return float(sentence["end_time"])
        return None

    def _run_task_message(self) -> dict[str, Any]:
        return {
            "header": {
                "action": "run-task",
                "task_id": self._task_id,
                "streaming": "duplex",
            },
            "payload": {
                "task_group": "audio",
                "task": "asr",
                "function": "recognition",
                "model": self._model,
                "parameters": {
                    "sample_rate": self._sample_rate,
                    "format": "pcm",
                    "max_sentence_silence": 400,
                    "heartbeat": True,
                    "vocabulary": {
                        "Redis": 5,
                        "MySQL": 5,
                        "JVM": 5,
                        "AQS": 5,
                        "Spring": 5,
                    },
                },
                "input": {},
            },
        }

    def _finish_task_message(self) -> dict[str, Any]:
        return {
            "header": {
                "action": "finish-task",
                "task_id": self._task_id,
                "streaming": "duplex",
            },
            "payload": {"input": {}},
        }
