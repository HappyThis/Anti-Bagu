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
DEFAULT_PROMPT = "9.9和9.11哪个大？请直接给出结论，并用一句话解释。"


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def dump_model(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    if hasattr(value, "model_dump"):
        return value.model_dump()
    return json.loads(json.dumps(value, default=str))


def run_test(client: OpenAI, prompt: str, thinking_enabled: bool) -> dict[str, Any]:
    started_at = time.perf_counter()
    first_event_at: float | None = None
    first_reasoning_at: float | None = None
    first_text_at: float | None = None
    reasoning_chunks: list[str] = []
    text_chunks: list[str] = []
    usage: dict[str, Any] | None = None

    request: dict[str, Any] = {
        "model": "deepseek-v4-flash",
        "messages": [{"role": "user", "content": prompt}],
        "stream": True,
        "max_tokens": 4096,
        "stream_options": {"include_usage": True},
        "extra_body": {
            "thinking": {"type": "enabled" if thinking_enabled else "disabled"}
        },
    }
    if thinking_enabled:
        request["reasoning_effort"] = "high"
    else:
        request["temperature"] = 0.1

    stream = client.chat.completions.create(**request)
    for chunk in stream:
        now = time.perf_counter()
        if first_event_at is None:
            first_event_at = now

        if chunk.usage is not None:
            usage = dump_model(chunk.usage)
        if not chunk.choices:
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
        "model": "deepseek-v4-flash",
        "thinking_enabled": thinking_enabled,
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
    }


def main() -> int:
    load_env_file(REPO_ROOT / ".env.local")
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        print("DEEPSEEK_API_KEY is not set", file=sys.stderr)
        return 1

    prompt = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_PROMPT
    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
    thinking_modes = [
        value.strip().lower() == "enabled"
        for value in os.environ.get(
            "DEEPSEEK_THINKING_MODES", "disabled,enabled"
        ).split(",")
    ]
    results = [run_test(client, prompt, thinking_enabled) for thinking_enabled in thinking_modes]
    print(json.dumps({"prompt": prompt, "results": results}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
