#!/usr/bin/env python3

from __future__ import annotations

import json
import os
import statistics
import threading
import time
from pathlib import Path
from typing import Any

from openai import OpenAI


ROOT = Path(__file__).resolve().parent.parent


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def run_once(api_key: str, run_number: int) -> dict[str, Any]:
    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
    request_started = time.perf_counter()
    stream = client.chat.completions.create(
        model="deepseek-v4-flash",
        messages=[
            {
                "role": "user",
                "content": "请详细设计一个十亿级日请求的支付系统，分析分片、幂等、事务、缓存、消息队列、容灾和扩容。",
            }
        ],
        stream=True,
        max_tokens=4096,
        reasoning_effort="high",
        extra_body={"thinking": {"type": "enabled"}},
    )
    stream_created = time.perf_counter()
    reader_stopped = threading.Event()
    first_delta_at: float | None = None
    chunks_received = 0
    reader_error: str | None = None

    def read_stream() -> None:
        nonlocal first_delta_at, chunks_received, reader_error
        try:
            for chunk in stream:
                if chunk.choices:
                    delta = chunk.choices[0].delta
                    if getattr(delta, "reasoning_content", None) or getattr(delta, "content", None):
                        if first_delta_at is None:
                            first_delta_at = time.perf_counter()
                        chunks_received += 1
        except Exception as exc:
            reader_error = f"{type(exc).__name__}: {exc}"
        finally:
            reader_stopped.set()

    reader = threading.Thread(target=read_stream, daemon=True)
    reader.start()
    time.sleep(0.3)
    cancel_started = time.perf_counter()
    stream.close()
    cancel_returned = time.perf_counter()
    stopped = reader_stopped.wait(timeout=2)
    reader.join(timeout=0.1)
    stopped_at = time.perf_counter()

    return {
        "run": run_number,
        "stream_creation_seconds": stream_created - request_started,
        "first_delta_seconds": (
            first_delta_at - request_started if first_delta_at else None
        ),
        "chunks_before_cancel": chunks_received,
        "close_call_seconds": cancel_returned - cancel_started,
        "reader_stop_after_cancel_seconds": stopped_at - cancel_started,
        "reader_stopped": stopped,
        "reader_error": reader_error,
    }


def main() -> int:
    load_env_file(ROOT / ".env.local")
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        raise SystemExit("DEEPSEEK_API_KEY is not set")
    results = [run_once(api_key, run_number) for run_number in range(1, 6)]
    stop_times = [result["reader_stop_after_cancel_seconds"] for result in results]
    output = {
        "summary": {
            "runs": len(results),
            "all_readers_stopped": all(result["reader_stopped"] for result in results),
            "max_reader_stop_after_cancel_seconds": max(stop_times),
            "median_reader_stop_after_cancel_seconds": statistics.median(stop_times),
            "reader_errors": sum(result["reader_error"] is not None for result in results),
        },
        "results": results,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
