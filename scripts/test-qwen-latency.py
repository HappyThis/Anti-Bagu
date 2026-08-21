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
DEFAULT_BASE_URL = (
    "https://dashscope.aliyuncs.com/"
    "api/v2/apps/protocols/compatible-mode/v1"
)
DEFAULT_MODEL = "qwen3.7-flash"
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


def event_delta(event: Any) -> str:
    delta = getattr(event, "delta", None)
    return delta if isinstance(delta, str) else ""


def run_test(
    client: OpenAI,
    model: str,
    prompt: str,
    reasoning_effort: str,
) -> dict[str, Any]:
    started_at = time.perf_counter()
    first_event_at: float | None = None
    first_reasoning_at: float | None = None
    first_text_at: float | None = None
    reasoning_chunks: list[str] = []
    text_chunks: list[str] = []
    event_types: list[str] = []
    usage: dict[str, Any] | None = None

    stream = client.responses.create(
        model=model,
        input=prompt,
        stream=True,
        reasoning={"effort": reasoning_effort},
    )

    for event in stream:
        now = time.perf_counter()
        event_type = getattr(event, "type", type(event).__name__)
        if event_type not in event_types:
            event_types.append(event_type)
        if first_event_at is None:
            first_event_at = now

        delta = event_delta(event)
        if "reasoning" in event_type and delta:
            if first_reasoning_at is None:
                first_reasoning_at = now
            reasoning_chunks.append(delta)
        elif event_type == "response.output_text.delta" and delta:
            if first_text_at is None:
                first_text_at = now
            text_chunks.append(delta)

        if event_type == "response.completed":
            response = getattr(event, "response", None)
            response_usage = getattr(response, "usage", None)
            if response_usage is not None:
                if hasattr(response_usage, "model_dump"):
                    usage = response_usage.model_dump()
                else:
                    usage = json.loads(json.dumps(response_usage, default=str))

    completed_at = time.perf_counter()
    return {
        "model": model,
        "reasoning_effort": reasoning_effort,
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
        "event_types": event_types,
    }


def main() -> int:
    load_env_file(REPO_ROOT / ".env.local")
    api_key = os.environ.get("DASHSCOPE_API_KEY")
    if not api_key:
        print("DASHSCOPE_API_KEY is not set", file=sys.stderr)
        return 1

    model = os.environ.get("DASHSCOPE_QWEN_MODEL", DEFAULT_MODEL)
    base_url = os.environ.get("DASHSCOPE_RESPONSES_BASE_URL", DEFAULT_BASE_URL)
    prompt = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_PROMPT

    client = OpenAI(api_key=api_key, base_url=base_url)
    efforts = os.environ.get("QWEN_REASONING_EFFORTS", "none,minimal,low").split(",")
    results = [run_test(client, model, prompt, effort.strip()) for effort in efforts]
    print(json.dumps({"prompt": prompt, "results": results}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
