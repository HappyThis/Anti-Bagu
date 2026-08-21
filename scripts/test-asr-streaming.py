#!/usr/bin/env python3

from __future__ import annotations

import io
import json
import os
import sys
import threading
import time
import urllib.request
import uuid
import wave
from pathlib import Path
from typing import Any

import websocket


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_AUDIO_URL = (
    "https://dashscope.oss-cn-beijing.aliyuncs.com/"
    "samples/audio/paraformer/hello_world_female2.wav"
)
DEFAULT_WS_URL = "wss://dashscope.aliyuncs.com/api-ws/v1/inference"
SAMPLE_RATE = 16_000
SAMPLE_WIDTH = 2
CHANNELS = 1
CHUNK_DURATION_MS = 100
CHUNK_SIZE = SAMPLE_RATE * SAMPLE_WIDTH * CHUNK_DURATION_MS // 1000
TRAILING_SILENCE_MS = 1_000


def load_env_file(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def download_pcm(audio_url: str) -> tuple[bytes, float]:
    with urllib.request.urlopen(audio_url, timeout=30) as response:
        wav_bytes = response.read()

    with wave.open(io.BytesIO(wav_bytes), "rb") as audio:
        actual_format = (
            audio.getframerate(),
            audio.getsampwidth(),
            audio.getnchannels(),
        )
        expected_format = (SAMPLE_RATE, SAMPLE_WIDTH, CHANNELS)
        if actual_format != expected_format:
            raise ValueError(
                f"Expected WAV format {expected_format}, received {actual_format}"
            )
        pcm = audio.readframes(audio.getnframes())

    duration_seconds = len(pcm) / (SAMPLE_RATE * SAMPLE_WIDTH * CHANNELS)
    return pcm, duration_seconds


def latest_audio_time_seconds(sentence: dict[str, Any]) -> float | None:
    words = sentence.get("words") or []
    word_end_times = [word.get("end_time") for word in words if word.get("end_time")]
    if word_end_times:
        return max(word_end_times) / 1000

    sentence_end_time = sentence.get("end_time")
    if sentence_end_time is not None:
        return sentence_end_time / 1000

    return None


def main() -> int:
    load_env_file(REPO_ROOT / ".env.local")

    api_key = os.environ.get("DASHSCOPE_API_KEY")
    if not api_key:
        print("DASHSCOPE_API_KEY is not set", file=sys.stderr)
        return 1

    audio_url = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_AUDIO_URL
    ws_url = os.environ.get("DASHSCOPE_WS_URL", DEFAULT_WS_URL)
    pcm, source_duration_seconds = download_pcm(audio_url)

    task_id = uuid.uuid4().hex
    started_at = time.perf_counter()
    task_started_event = threading.Event()
    final_event = threading.Event()
    finished_event = threading.Event()
    failed_event = threading.Event()
    lock = threading.Lock()
    state: dict[str, Any] = {
        "audio_start": None,
        "speech_send_end": None,
        "audio_send_end": None,
        "first_result": None,
        "final_result": None,
        "events": [],
        "error": None,
    }

    def elapsed() -> float:
        return time.perf_counter() - started_at

    def send_run_task(ws: websocket.WebSocketApp) -> None:
        ws.send(
            json.dumps(
                {
                    "header": {
                        "action": "run-task",
                        "task_id": task_id,
                        "streaming": "duplex",
                    },
                    "payload": {
                        "task_group": "audio",
                        "task": "asr",
                        "function": "recognition",
                        "model": "qwen-audio-3.0-asr-flash-streaming",
                        "parameters": {
                            "sample_rate": SAMPLE_RATE,
                            "format": "pcm",
                            "max_sentence_silence": 400,
                            "heartbeat": True,
                            "vocabulary": {
                                "Redis": 5,
                                "MySQL": 5,
                                "JVM": 5,
                            },
                        },
                        "input": {},
                    },
                },
                ensure_ascii=False,
            )
        )

    def send_finish_task(ws: websocket.WebSocketApp) -> None:
        ws.send(
            json.dumps(
                {
                    "header": {
                        "action": "finish-task",
                        "task_id": task_id,
                        "streaming": "duplex",
                    },
                    "payload": {"input": {}},
                }
            )
        )

    def send_audio_stream(ws: websocket.WebSocketApp) -> None:
        with lock:
            state["audio_start"] = elapsed()
        next_send_at = time.perf_counter()

        for offset in range(0, len(pcm), CHUNK_SIZE):
            ws.send(pcm[offset : offset + CHUNK_SIZE], opcode=websocket.ABNF.OPCODE_BINARY)
            next_send_at += CHUNK_DURATION_MS / 1000
            time.sleep(max(0, next_send_at - time.perf_counter()))

        with lock:
            state["speech_send_end"] = elapsed()

        silence_chunk = bytes(CHUNK_SIZE)
        for _ in range(TRAILING_SILENCE_MS // CHUNK_DURATION_MS):
            ws.send(silence_chunk, opcode=websocket.ABNF.OPCODE_BINARY)
            next_send_at += CHUNK_DURATION_MS / 1000
            time.sleep(max(0, next_send_at - time.perf_counter()))

        with lock:
            state["audio_send_end"] = elapsed()

        final_event.wait(timeout=3)
        send_finish_task(ws)

    def on_open(ws: websocket.WebSocketApp) -> None:
        with lock:
            state["connection_open"] = elapsed()
        send_run_task(ws)

    def on_message(ws: websocket.WebSocketApp, data: str) -> None:
        message = json.loads(data)
        event_name = message.get("header", {}).get("event")
        now = elapsed()

        if event_name == "task-started":
            with lock:
                state["task_started"] = now
            task_started_event.set()
            threading.Thread(target=send_audio_stream, args=(ws,), daemon=True).start()
            return

        if event_name == "result-generated":
            sentence = message.get("payload", {}).get("output", {}).get("sentence", {})
            event_record = {
                "received_seconds": now,
                "text": sentence.get("text", ""),
                "sentence_end": bool(sentence.get("sentence_end")),
                "audio_time_seconds": latest_audio_time_seconds(sentence),
            }
            with lock:
                state["events"].append(event_record)
                if state["first_result"] is None and event_record["text"]:
                    state["first_result"] = event_record
                if event_record["sentence_end"]:
                    state["final_result"] = event_record
                    final_event.set()
            return

        if event_name == "task-finished":
            with lock:
                state["task_finished"] = now
                state["usage"] = message.get("payload", {}).get("usage")
            finished_event.set()
            ws.close()
            return

        if event_name == "task-failed":
            with lock:
                state["error"] = message.get("header", {}).get("error_message")
            failed_event.set()
            ws.close()

    def on_error(_ws: websocket.WebSocketApp, error: object) -> None:
        with lock:
            state["error"] = str(error)
        failed_event.set()

    def on_close(
        _ws: websocket.WebSocketApp,
        close_status_code: int | None,
        close_message: str | None,
    ) -> None:
        with lock:
            state["close_status_code"] = close_status_code
            state["close_message"] = close_message

    ws = websocket.WebSocketApp(
        ws_url,
        header={"Authorization": f"bearer {api_key}"},
        on_open=on_open,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close,
    )
    ws_thread = threading.Thread(target=ws.run_forever, daemon=True)
    ws_thread.start()

    if not task_started_event.wait(timeout=10):
        ws.close()
        print(json.dumps({"error": state.get("error") or "task start timeout"}))
        return 1

    finished_event.wait(timeout=source_duration_seconds + 10)
    if failed_event.is_set() or not finished_event.is_set():
        ws.close()
        print(json.dumps({"error": state.get("error") or "task finish timeout"}))
        return 1

    audio_start = state["audio_start"]
    first_result = state["first_result"]
    final_result = state["final_result"]
    speech_send_end = state["speech_send_end"]

    result = {
        "model": "qwen-audio-3.0-asr-flash-streaming",
        "source_duration_seconds": source_duration_seconds,
        "connection_seconds": state["connection_open"],
        "task_start_seconds": state["task_started"],
        "first_partial_from_audio_start_seconds": (
            first_result["received_seconds"] - audio_start if first_result else None
        ),
        "first_partial_lag_seconds": (
            first_result["received_seconds"]
            - audio_start
            - first_result["audio_time_seconds"]
            if first_result and first_result["audio_time_seconds"] is not None
            else None
        ),
        "final_from_audio_start_seconds": (
            final_result["received_seconds"] - audio_start if final_result else None
        ),
        "final_lag_from_recognized_speech_end_seconds": (
            final_result["received_seconds"]
            - audio_start
            - final_result["audio_time_seconds"]
            if final_result and final_result["audio_time_seconds"] is not None
            else None
        ),
        "final_after_source_send_end_seconds": (
            final_result["received_seconds"] - speech_send_end
            if final_result and speech_send_end is not None
            else None
        ),
        "task_total_seconds": state["task_finished"],
        "transcript": final_result["text"] if final_result else None,
        "usage": state.get("usage"),
        "events": state["events"],
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
