#!/usr/bin/env python3

from __future__ import annotations

import io
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
import uuid
import wave
from pathlib import Path
from typing import Any

import websocket
from openai import OpenAI

from local_route_gate import requires_thinking


REPO_ROOT = Path(__file__).resolve().parent.parent
PROMPT_PATH = REPO_ROOT / "tests" / "fixtures" / "focus_responder_prompt.txt"
SYSTEM_PROMPT = PROMPT_PATH.read_text(encoding="utf-8").strip()
WS_URL = "wss://dashscope.aliyuncs.com/api-ws/v1/inference"
SAMPLE_RATE = 16_000
CHUNK_MS = 100
CHUNK_SIZE = SAMPLE_RATE * 2 * CHUNK_MS // 1000

CASES = [
    {
        "id": "fast_redis",
        "text": "请你说一下 Redis 为什么这么快？",
        "expected_mode": "FAST",
        "required_transcript": ["Redis", "快"],
    },
    {
        "id": "fast_volatile",
        "text": "Java 里面的 volatile 关键字有什么作用？",
        "expected_mode": "FAST",
        "required_transcript": ["volatile", "作用"],
    },
    {
        "id": "think_decimal",
        "text": "九点九和九点一一哪个更大？请解释计算过程。",
        "expected_mode": "THINK",
        "required_transcript": ["9.9", "9.11"],
        "required_answer": ["9.9"],
    },
    {
        "id": "think_qps",
        "text": "系统有一亿用户，日活百分之一，每人每天五次请求，峰值是平均值的八倍，请估算峰值 QPS。",
        "expected_mode": "THINK",
        "required_transcript": ["QPS"],
        "required_answer": ["463"],
    },
]


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def synthesize_pcm(text: str) -> bytes:
    with tempfile.TemporaryDirectory(prefix="anti-bagu-e2e-") as temp_dir:
        aiff_path = Path(temp_dir) / "question.aiff"
        pcm_path = Path(temp_dir) / "question.pcm"
        subprocess.run(
            ["say", "-v", "Tingting", "-r", "185", "-o", str(aiff_path), text],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        subprocess.run(
            [
                "ffmpeg",
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(aiff_path),
                "-ar",
                str(SAMPLE_RATE),
                "-ac",
                "1",
                "-f",
                "s16le",
                str(pcm_path),
            ],
            check=True,
        )
        return pcm_path.read_bytes()


def stream_asr(pcm: bytes, api_key: str) -> dict[str, Any]:
    task_id = uuid.uuid4().hex
    started_at = time.perf_counter()
    task_started_event = threading.Event()
    final_event = threading.Event()
    finished_event = threading.Event()
    state: dict[str, Any] = {
        "audio_start": None,
        "speech_send_end": None,
        "final": None,
        "error": None,
    }

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
                            "vocabulary": {
                                "Redis": 5,
                                "volatile": 5,
                                "QPS": 5,
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
            next_send_at += CHUNK_MS / 1000
            time.sleep(max(0, next_send_at - time.perf_counter()))
        state["speech_send_end"] = elapsed()
        for _ in range(10):
            ws.send(bytes(CHUNK_SIZE), opcode=websocket.ABNF.OPCODE_BINARY)
            next_send_at += CHUNK_MS / 1000
            time.sleep(max(0, next_send_at - time.perf_counter()))
        final_event.wait(timeout=3)
        send_finish(ws)

    def on_open(ws: websocket.WebSocketApp) -> None:
        send_run(ws)

    def on_message(ws: websocket.WebSocketApp, data: str) -> None:
        message = json.loads(data)
        event = message.get("header", {}).get("event")
        if event == "task-started":
            task_started_event.set()
            threading.Thread(target=send_audio, args=(ws,), daemon=True).start()
        elif event == "result-generated":
            sentence = message.get("payload", {}).get("output", {}).get("sentence", {})
            if sentence.get("sentence_end"):
                state["final"] = {
                    "received": elapsed(),
                    "text": sentence.get("text", ""),
                    "audio_end": (sentence.get("end_time") or 0) / 1000,
                }
                final_event.set()
        elif event == "task-finished":
            finished_event.set()
            ws.close()
        elif event == "task-failed":
            state["error"] = message.get("header", {}).get("error_message")
            finished_event.set()
            ws.close()

    def on_error(_ws: websocket.WebSocketApp, error: object) -> None:
        state["error"] = str(error)
        finished_event.set()

    ws = websocket.WebSocketApp(
        WS_URL,
        header={"Authorization": f"bearer {api_key}"},
        on_open=on_open,
        on_message=on_message,
        on_error=on_error,
    )
    thread = threading.Thread(target=ws.run_forever, daemon=True)
    thread.start()
    if not task_started_event.wait(timeout=10):
        ws.close()
        raise RuntimeError(state["error"] or "ASR task start timeout")
    if not finished_event.wait(timeout=len(pcm) / (SAMPLE_RATE * 2) + 10):
        ws.close()
        raise RuntimeError("ASR task finish timeout")
    if state["error"] or not state["final"]:
        raise RuntimeError(state["error"] or "ASR returned no final transcript")

    final = state["final"]
    audio_start = state["audio_start"]
    final_lag = final["received"] - audio_start - final["audio_end"]
    return {
        "transcript": final["text"],
        "audio_duration_seconds": len(pcm) / (SAMPLE_RATE * 2),
        "final_lag_seconds": final_lag,
    }


def parse_json_stream(
    client: OpenAI, transcript: str
) -> dict[str, Any]:
    payload = {
        "current_focus": None,
        "conversation": [{"speaker": "interviewer", "text": transcript}],
    }
    started_at = time.perf_counter()
    chunks: list[str] = []
    first_text_at: float | None = None
    mode_at: float | None = None
    answer_at: float | None = None
    stream = client.chat.completions.create(
        model="deepseek-v4-flash",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ],
        stream=True,
        max_tokens=800,
        temperature=0.1,
        response_format={"type": "json_object"},
        extra_body={"thinking": {"type": "disabled"}},
    )
    for chunk in stream:
        if not chunk.choices:
            continue
        content = getattr(chunk.choices[0].delta, "content", None)
        if not content:
            continue
        now = time.perf_counter()
        if first_text_at is None:
            first_text_at = now
        chunks.append(content)
        accumulated = "".join(chunks)
        if mode_at is None and re.search(r'"answer_mode"\s*:\s*"(?:FAST|THINK)"', accumulated):
            mode_at = now
        if answer_at is None and re.search(r'"answer"\s*:\s*"[^"}]', accumulated):
            answer_at = now
    completed_at = time.perf_counter()
    parsed = json.loads("".join(chunks))
    return {
        "parsed": parsed,
        "first_text_seconds": first_text_at - started_at if first_text_at else None,
        "mode_seconds": mode_at - started_at if mode_at else None,
        "answer_seconds": answer_at - started_at if answer_at else None,
        "total_seconds": completed_at - started_at,
    }


def run_thinking_answer(
    client: OpenAI, focus_question: str, original_transcript: str
) -> dict[str, Any]:
    started_at = time.perf_counter()
    first_text_at: float | None = None
    chunks: list[str] = []
    stream = client.chat.completions.create(
        model="deepseek-v4-flash",
        messages=[
            {
                "role": "system",
                "content": "你是计算机面试助手。请准确计算或推导，必须保留并使用输入中的全部数字、代码和约束。先给结论，再简洁说明步骤，不用 Markdown，不超过180个中文字符。",
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "focus_question": focus_question,
                        "original_transcript": original_transcript,
                    },
                    ensure_ascii=False,
                ),
            },
        ],
        stream=True,
        max_tokens=2000,
        reasoning_effort="high",
        extra_body={"thinking": {"type": "enabled"}},
    )
    for chunk in stream:
        if not chunk.choices:
            continue
        content = getattr(chunk.choices[0].delta, "content", None)
        if content:
            if first_text_at is None:
                first_text_at = time.perf_counter()
            chunks.append(content)
    completed_at = time.perf_counter()
    return {
        "first_text_seconds": first_text_at - started_at if first_text_at else None,
        "total_seconds": completed_at - started_at,
        "answer": "".join(chunks),
    }


def main() -> int:
    load_env_file(REPO_ROOT / ".env.local")
    dashscope_key = os.environ.get("DASHSCOPE_API_KEY")
    deepseek_key = os.environ.get("DEEPSEEK_API_KEY")
    if not dashscope_key or not deepseek_key:
        print("DASHSCOPE_API_KEY and DEEPSEEK_API_KEY are required", file=sys.stderr)
        return 1

    client = OpenAI(api_key=deepseek_key, base_url="https://api.deepseek.com")
    results: list[dict[str, Any]] = []
    case_filter = {
        value.strip()
        for value in os.environ.get("E2E_CASES", "").split(",")
        if value.strip()
    }
    selected_cases = [case for case in CASES if not case_filter or case["id"] in case_filter]
    for case in selected_cases:
        pcm = synthesize_pcm(case["text"])
        asr = stream_asr(pcm, dashscope_key)
        locally_routed = requires_thinking(asr["transcript"])
        if locally_routed:
            route = None
            parsed = {
                "action": "RESPOND",
                "answer_mode": "THINK",
                "focus_question": asr["transcript"],
                "answer": "",
            }
        else:
            route = parse_json_stream(client, asr["transcript"])
            parsed = route["parsed"]
        mode = parsed.get("answer_mode")
        if mode == "THINK":
            thinking = run_thinking_answer(
                client, parsed["focus_question"], asr["transcript"]
            )
            router_delay = route["total_seconds"] if route else 0
            model_answer_delay = router_delay + thinking["first_text_seconds"]
            answer = thinking["answer"]
        else:
            thinking = None
            model_answer_delay = route["answer_seconds"]
            answer = parsed.get("answer", "")
        transcript_normalized = asr["transcript"].replace(" ", "").lower()
        required_ok = all(
            term.replace(" ", "").lower() in transcript_normalized
            for term in case["required_transcript"]
        )
        answer_ok = all(
            term.replace(" ", "").lower() in answer.replace(" ", "").lower()
            for term in case.get("required_answer", [])
        )
        results.append(
            {
                "id": case["id"],
                "expected_mode": case["expected_mode"],
                "actual_mode": mode,
                "mode_correct": mode == case["expected_mode"],
                "locally_routed": locally_routed,
                "focus_question": parsed.get("focus_question"),
                "source_text": case["text"],
                "transcript": asr["transcript"],
                "transcript_terms_correct": required_ok,
                "answer_terms_correct": answer_ok,
                "audio_duration_seconds": asr["audio_duration_seconds"],
                "asr_final_lag_seconds": asr["final_lag_seconds"],
                "router_first_text_seconds": route["first_text_seconds"] if route else None,
                "router_mode_seconds": route["mode_seconds"] if route else None,
                "model_answer_delay_seconds": model_answer_delay,
                "end_to_end_after_speech_seconds": (
                    asr["final_lag_seconds"] + model_answer_delay
                ),
                "answer": answer,
                "thinking_call": thinking,
            }
        )
    print(json.dumps({"results": results}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
