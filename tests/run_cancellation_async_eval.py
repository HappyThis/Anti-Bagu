#!/usr/bin/env python3

from __future__ import annotations

import asyncio
import json
import os
import statistics
import time
from pathlib import Path
from typing import Any

from openai import AsyncOpenAI


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


async def run_once(api_key: str, run_number: int) -> dict[str, Any]:
    client = AsyncOpenAI(api_key=api_key, base_url="https://api.deepseek.com")
    request_started = time.perf_counter()
    stream = await client.chat.completions.create(
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
    first_delta_at: float | None = None
    chunks_received = 0

    async def consume() -> None:
        nonlocal first_delta_at, chunks_received
        async for chunk in stream:
            if chunk.choices:
                delta = chunk.choices[0].delta
                if getattr(delta, "reasoning_content", None) or getattr(delta, "content", None):
                    if first_delta_at is None:
                        first_delta_at = time.perf_counter()
                    chunks_received += 1

    consumer = asyncio.create_task(consume())
    await asyncio.sleep(0.3)
    cancel_started = time.perf_counter()
    consumer.cancel()
    cancelled_cleanly = False
    try:
        await consumer
    except asyncio.CancelledError:
        cancelled_cleanly = True
    await stream.close()
    await client.close()
    cancel_completed = time.perf_counter()

    return {
        "run": run_number,
        "stream_creation_seconds": stream_created - request_started,
        "first_delta_seconds": first_delta_at - request_started if first_delta_at else None,
        "chunks_before_cancel": chunks_received,
        "cancel_completed_seconds": cancel_completed - cancel_started,
        "cancelled_cleanly": cancelled_cleanly,
    }


async def async_main() -> int:
    load_env_file(ROOT / ".env.local")
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        raise SystemExit("DEEPSEEK_API_KEY is not set")
    results = [await run_once(api_key, run_number) for run_number in range(1, 6)]
    cancel_times = [result["cancel_completed_seconds"] for result in results]
    output = {
        "summary": {
            "runs": len(results),
            "all_cancelled_cleanly": all(result["cancelled_cleanly"] for result in results),
            "median_cancel_seconds": statistics.median(cancel_times),
            "max_cancel_seconds": max(cancel_times),
        },
        "results": results,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    return asyncio.run(async_main())


if __name__ == "__main__":
    raise SystemExit(main())
