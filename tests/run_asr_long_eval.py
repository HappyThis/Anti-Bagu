#!/usr/bin/env python3

from __future__ import annotations

import json
import os
import statistics
import threading
import time
import uuid
from pathlib import Path
from typing import Any

import websocket

from run_e2e_eval import CHUNK_SIZE, SAMPLE_RATE, WS_URL, load_env_file, synthesize_pcm


ROOT = Path(__file__).resolve().parent.parent
SILENCE_BETWEEN_MS = 900
QUESTIONS = [
    ("请你说一下 Redis 为什么这么快？", ["redis", "快"]),
    ("Java 里面的 volatile 关键字有什么作用？", ["volatile", "作用"]),
    ("MySQL 索引为什么通常使用 B 加树？", ["mysql", "索引"]),
    ("请说一下 TCP 三次握手的过程。", ["tcp", "三次握手"]),
    ("ThreadLocal 为什么可能导致内存泄漏？", ["threadlocal", "内存泄漏"]),
    ("解释一下分布式系统中的 CAP。", ["cap"]),
    ("HTTP 二相比 HTTP 一点一有哪些改进？", ["http", "改进"]),
    ("产生死锁的四个必要条件是什么？", ["死锁", "条件"]),
]


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int((len(ordered) * fraction + 0.999999)) - 1))
    return ordered[index]


def normalize(text: str) -> str:
    return text.replace(" ", "").lower()


def main() -> int:
    load_env_file(ROOT / ".env.local")
    api_key = os.environ.get("DASHSCOPE_API_KEY")
    if not api_key:
        raise SystemExit("DASHSCOPE_API_KEY is not set")

    separator = bytes(SAMPLE_RATE * 2 * SILENCE_BETWEEN_MS // 1000)
    pcm_parts: list[bytes] = []
    for text, _ in QUESTIONS:
        pcm_parts.append(synthesize_pcm(text))
        pcm_parts.append(separator)
    pcm = b"".join(pcm_parts)

    task_id = uuid.uuid4().hex
    started_at = time.perf_counter()
    task_started = threading.Event()
    finished = threading.Event()
    state: dict[str, Any] = {"audio_start": None, "finals": [], "error": None}

    def elapsed() -> float:
        return time.perf_counter() - started_at

    def send_run(ws: websocket.WebSocketApp) -> None:
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
                                "volatile": 5,
                                "MySQL": 5,
                                "B+树": 5,
                                "TCP": 5,
                                "ThreadLocal": 5,
                                "CAP": 5,
                                "HTTP/2": 5,
                                "HTTP/1.1": 5,
                            },
                        },
                        "input": {},
                    },
                },
                ensure_ascii=False,
            )
        )

    def send_finish(ws: websocket.WebSocketApp) -> None:
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

    def send_audio(ws: websocket.WebSocketApp) -> None:
        state["audio_start"] = elapsed()
        next_send_at = time.perf_counter()
        for offset in range(0, len(pcm), CHUNK_SIZE):
            ws.send(pcm[offset : offset + CHUNK_SIZE], opcode=websocket.ABNF.OPCODE_BINARY)
            next_send_at += 0.1
            time.sleep(max(0, next_send_at - time.perf_counter()))
        for _ in range(10):
            ws.send(bytes(CHUNK_SIZE), opcode=websocket.ABNF.OPCODE_BINARY)
            next_send_at += 0.1
            time.sleep(max(0, next_send_at - time.perf_counter()))
        send_finish(ws)

    def on_open(ws: websocket.WebSocketApp) -> None:
        send_run(ws)

    def on_message(ws: websocket.WebSocketApp, data: str) -> None:
        message = json.loads(data)
        event = message.get("header", {}).get("event")
        if event == "task-started":
            task_started.set()
            threading.Thread(target=send_audio, args=(ws,), daemon=True).start()
        elif event == "result-generated":
            sentence = message.get("payload", {}).get("output", {}).get("sentence", {})
            if sentence.get("sentence_end"):
                audio_end = (sentence.get("end_time") or 0) / 1000
                received = elapsed()
                state["finals"].append(
                    {
                        "text": sentence.get("text", ""),
                        "audio_end_seconds": audio_end,
                        "received_seconds": received,
                        "lag_seconds": received - state["audio_start"] - audio_end,
                    }
                )
        elif event == "task-finished":
            finished.set()
            ws.close()
        elif event == "task-failed":
            state["error"] = message.get("header", {}).get("error_message")
            finished.set()
            ws.close()

    def on_error(_ws: websocket.WebSocketApp, error: object) -> None:
        state["error"] = str(error)
        finished.set()

    ws = websocket.WebSocketApp(
        WS_URL,
        header={"Authorization": f"bearer {api_key}"},
        on_open=on_open,
        on_message=on_message,
        on_error=on_error,
    )
    thread = threading.Thread(target=ws.run_forever, daemon=True)
    thread.start()
    if not task_started.wait(timeout=10):
        ws.close()
        raise RuntimeError(state["error"] or "ASR task start timeout")
    audio_duration = len(pcm) / (SAMPLE_RATE * 2)
    if not finished.wait(timeout=audio_duration + 10):
        ws.close()
        raise RuntimeError("ASR long test timeout")
    if state["error"]:
        raise RuntimeError(state["error"])

    combined_transcript = normalize(" ".join(item["text"] for item in state["finals"]))
    matched = []
    for question, terms in QUESTIONS:
        matched.append(
            {
                "question": question,
                "matched": all(normalize(term) in combined_transcript for term in terms),
                "required_terms": terms,
            }
        )
    lags = [item["lag_seconds"] for item in state["finals"]]
    output = {
        "summary": {
            "audio_duration_seconds": audio_duration,
            "source_questions": len(QUESTIONS),
            "final_segments": len(state["finals"]),
            "matched_questions": sum(item["matched"] for item in matched),
            "final_lag_seconds": {
                "average": statistics.fmean(lags),
                "p50": statistics.median(lags),
                "p95": percentile(lags, 0.95),
                "max": max(lags),
            },
        },
        "matches": matched,
        "finals": state["finals"],
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
