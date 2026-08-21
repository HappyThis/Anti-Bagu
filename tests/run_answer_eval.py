#!/usr/bin/env python3

from __future__ import annotations

import concurrent.futures
import json
import os
import statistics
import sys
import time
from pathlib import Path
from typing import Any

from openai import OpenAI


REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_PATH = REPO_ROOT / "tests" / "fixtures" / "answer_cases.json"
PROMPT_PATH = REPO_ROOT / "tests" / "fixtures" / "bagu_answer_prompt.txt"
SYSTEM_PROMPT = PROMPT_PATH.read_text(encoding="utf-8").strip()


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int((len(ordered) * fraction + 0.999999)) - 1))
    return ordered[index]


def parse_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        stripped = "\n".join(lines[1:-1])
    return json.loads(stripped)


def contains(text: str, term: str) -> bool:
    return term.replace(" ", "").lower() in text.replace(" ", "").lower()


def run_case(
    case: dict[str, Any],
    api_key: str,
    base_url: str,
    model: str,
    provider: str,
    thinking_enabled: bool,
    grounding_enabled: bool,
) -> dict[str, Any]:
    client = OpenAI(api_key=api_key, base_url=base_url)
    user_payload = {
        "question": case["question"],
    }
    if grounding_enabled and case.get("grounding"):
        user_payload["verified_facts"] = case["grounding"]
    started_at = time.perf_counter()
    first_reasoning_at: float | None = None
    first_text_at: float | None = None
    reasoning_chunks: list[str] = []
    text_chunks: list[str] = []
    usage: Any = None

    try:
        request: dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": json.dumps(user_payload, ensure_ascii=False),
                },
            ],
            "stream": True,
            "max_tokens": 1200,
            "response_format": {"type": "json_object"},
            "stream_options": {"include_usage": True},
        }
        if provider == "deepseek":
            request["extra_body"] = {
                "thinking": {"type": "enabled" if thinking_enabled else "disabled"}
            }
            if thinking_enabled:
                request["reasoning_effort"] = "high"
            else:
                request["temperature"] = 0.1
        elif reasoning_effort := os.environ.get("ANSWER_EVAL_REASONING_EFFORT"):
            request["reasoning_effort"] = reasoning_effort

        stream = client.chat.completions.create(**request)
        for chunk in stream:
            now = time.perf_counter()
            if chunk.usage is not None:
                usage = (
                    chunk.usage.model_dump()
                    if hasattr(chunk.usage, "model_dump")
                    else chunk.usage
                )
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
        raw_text = "".join(text_chunks)
        parsed = parse_json_object(raw_text)
        error = None
    except Exception as exc:
        completed_at = time.perf_counter()
        raw_text = "".join(text_chunks)
        parsed = {}
        error = f"{type(exc).__name__}: {exc}"

    answer = str(parsed.get("answer", ""))
    missing_groups = [
        group
        for group in case["required_groups"]
        if not any(contains(answer, term) for term in group)
    ]
    forbidden_hits = [
        term for term in case.get("forbidden_terms", []) if contains(answer, term)
    ]
    leak_free = not any(
        marker in (raw_text + answer)
        for marker in ("<think>", "</think>", "Self-Correction", "Verification")
    )

    return {
        "id": case["id"],
        "model": model,
        "thinking": "enabled" if thinking_enabled else "disabled",
        "grounding": grounding_enabled,
        "action_correct": True,
        "answer_mode_correct": True,
        "knowledge_coverage": not missing_groups,
        "missing_groups": missing_groups,
        "forbidden_hits": forbidden_hits,
        "forbidden_clean": not forbidden_hits,
        "answer_characters": len(answer),
        "answer_within_limit": len(answer) <= 160,
        "leak_free": leak_free,
        "first_reasoning_seconds": (
            first_reasoning_at - started_at if first_reasoning_at else None
        ),
        "first_text_seconds": first_text_at - started_at if first_text_at else None,
        "total_seconds": completed_at - started_at,
        "reasoning_tokens": (
            usage.get("completion_tokens_details", {}).get("reasoning_tokens")
            if isinstance(usage, dict)
            and isinstance(usage.get("completion_tokens_details"), dict)
            else None
        ),
        "question": case["question"],
        "answer": answer,
        "error": error,
    }


def main() -> int:
    load_env_file(REPO_ROOT / ".env.local")
    provider = os.environ.get("ANSWER_EVAL_PROVIDER", "deepseek").strip().lower()
    base_url = os.environ.get("ANSWER_EVAL_BASE_URL", "https://api.deepseek.com")
    model = os.environ.get("ANSWER_EVAL_MODEL", "deepseek-v4-flash")
    api_key_env = os.environ.get("ANSWER_EVAL_API_KEY_ENV", "DEEPSEEK_API_KEY")
    api_key = os.environ.get(api_key_env)
    if not api_key:
        print(f"{api_key_env} is not set", file=sys.stderr)
        return 1

    cases = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    modes = [
        value.strip().lower() == "enabled"
        for value in os.environ.get(
            "ANSWER_EVAL_THINKING_MODES", "disabled,enabled"
        ).split(",")
    ]
    tasks = [(case, mode) for mode in modes for case in cases]
    concurrency = int(os.environ.get("ANSWER_EVAL_CONCURRENCY", "4"))
    grounding_enabled = (
        os.environ.get("ANSWER_EVAL_GROUNDING", "disabled").lower() == "enabled"
    )
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
        results = list(
            executor.map(
                lambda task: run_case(
                    task[0],
                    api_key,
                    base_url,
                    model,
                    provider,
                    task[1],
                    grounding_enabled,
                ),
                tasks,
            )
        )

    summaries: dict[str, Any] = {}
    for mode_name in ("disabled", "enabled"):
        mode_results = [result for result in results if result["thinking"] == mode_name]
        if not mode_results:
            continue
        passed = [
            result
            for result in mode_results
            if result["action_correct"]
            and result["answer_mode_correct"]
            and result["knowledge_coverage"]
            and result["forbidden_clean"]
            and result["answer_within_limit"]
            and result["leak_free"]
            and result["error"] is None
        ]
        first_text = [
            result["first_text_seconds"]
            for result in mode_results
            if result["first_text_seconds"] is not None
        ]
        total = [result["total_seconds"] for result in mode_results]
        summaries[mode_name] = {
            "cases": len(mode_results),
            "passed": len(passed),
            "pass_rate": len(passed) / len(mode_results),
            "knowledge_coverage_rate": sum(
                result["knowledge_coverage"] for result in mode_results
            )
            / len(mode_results),
            "forbidden_failures": sum(
                not result["forbidden_clean"] for result in mode_results
            ),
            "length_failures": sum(
                not result["answer_within_limit"] for result in mode_results
            ),
            "json_errors": sum(result["error"] is not None for result in mode_results),
            "thinking_leaks": sum(not result["leak_free"] for result in mode_results),
            "first_text_seconds": {
                "average": statistics.fmean(first_text),
                "p50": statistics.median(first_text),
                "p95": percentile(first_text, 0.95),
                "max": max(first_text),
            },
            "total_seconds": {
                "average": statistics.fmean(total),
                "p50": statistics.median(total),
                "p95": percentile(total, 0.95),
                "max": max(total),
            },
        }

    print(json.dumps({"summaries": summaries, "results": results}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
