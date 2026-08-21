#!/usr/bin/env python3

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any

from openai import OpenAI


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
DEFAULT_MODEL = "qwen3.7-flash"
DEFAULT_BUDGETS = (64, 128, 256)


def load_env_file(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def model_dump(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    if hasattr(value, "model_dump"):
        return value.model_dump()
    return json.loads(json.dumps(value, default=str))


def run_test(
    client: OpenAI,
    model: str,
    prompt: str,
    thinking_budget: int,
) -> dict[str, Any]:
    started_at = time.perf_counter()
    first_event_at: float | None = None
    first_reasoning_at: float | None = None
    first_text_at: float | None = None
    reasoning_chunks: list[str] = []
    text_chunks: list[str] = []
    usage: dict[str, Any] | None = None
    non_choice_events: list[dict[str, Any]] = []

    stream = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        stream=True,
        temperature=0.1,
        max_tokens=512,
        stream_options={"include_usage": True},
        extra_body={
            "enable_thinking": True,
            "thinking_budget": thinking_budget,
        },
    )

    for chunk in stream:
        now = time.perf_counter()
        if first_event_at is None:
            first_event_at = now

        usage_data = getattr(chunk, "usage", None)
        if usage_data is not None:
            usage = model_dump(usage_data)

        if not chunk.choices:
            dumped_chunk = model_dump(chunk)
            if dumped_chunk is not None:
                non_choice_events.append(dumped_chunk)
            continue

        delta = chunk.choices[0].delta
        reasoning = getattr(delta, "reasoning_content", None)
        content = getattr(delta, "content", None)

        if reasoning:
            if first_reasoning_at is None:
                first_reasoning_at = now
            reasoning_chunks.append(reasoning)

        if content:
            if first_text_at is None:
                first_text_at = now
            text_chunks.append(content)

    completed_at = time.perf_counter()
    return {
        "model": model,
        "thinking_budget": thinking_budget,
        "first_event_seconds": (
            first_event_at - started_at if first_event_at is not None else None
        ),
        "first_reasoning_seconds": (
            first_reasoning_at - started_at if first_reasoning_at is not None else None
        ),
        "first_text_seconds": (
            first_text_at - started_at if first_text_at is not None else None
        ),
        "total_seconds": completed_at - started_at,
        "reasoning_characters": len("".join(reasoning_chunks)),
        "text_characters": len("".join(text_chunks)),
        "answer": "".join(text_chunks),
        "usage": usage,
        "non_choice_events": non_choice_events,
    }


def main() -> int:
    load_env_file(REPO_ROOT / ".env.local")
    api_key = os.environ.get("DASHSCOPE_API_KEY")
    if not api_key:
        print("DASHSCOPE_API_KEY is not set", file=sys.stderr)
        return 1

    model = os.environ.get("DASHSCOPE_QWEN_MODEL", DEFAULT_MODEL)
    base_url = os.environ.get("DASHSCOPE_CHAT_BASE_URL", DEFAULT_BASE_URL)
    prompt = sys.argv[1] if len(sys.argv) > 1 else "9.9和9.11哪个大？请直接给出结论，并用一句话解释。"
    budgets = tuple(
        int(value)
        for value in os.environ.get("QWEN_THINKING_BUDGETS", "64,128,256").split(",")
    )

    client = OpenAI(api_key=api_key, base_url=base_url)
    results = [run_test(client, model, prompt, budget) for budget in budgets]
    print(json.dumps({"prompt": prompt, "results": results}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
