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
FIXTURE_PATH = REPO_ROOT / "tests" / "fixtures" / "focus_cases.json"
PROMPT_PATH = REPO_ROOT / "tests" / "fixtures" / "focus_responder_prompt.txt"
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


def run_case(
    case: dict[str, Any], api_key: str, thinking_enabled: bool
) -> dict[str, Any]:
    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
    user_payload = {
        "current_focus": case.get("current_focus"),
        "conversation": case["conversation"],
    }
    started_at = time.perf_counter()
    first_reasoning_at: float | None = None
    first_text_at: float | None = None
    reasoning_chunks: list[str] = []
    text_chunks: list[str] = []
    usage: Any = None

    try:
        request: dict[str, Any] = {
            "model": "deepseek-v4-flash",
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

    action = str(parsed.get("action", "")).upper()
    answer_mode = str(parsed.get("answer_mode", "")).upper()
    question = str(parsed.get("focus_question", ""))
    answer = str(parsed.get("answer", ""))
    required_terms = case.get("required_question_terms", [])
    missing_terms = [
        term for term in required_terms if term.lower() not in question.lower()
    ]
    expected_action = "WAIT" if case["expected_action"] == "WAIT" else "RESPOND"
    action_correct = action == expected_action
    wait_fields_correct = (
        expected_action != "WAIT" or (question.strip() == "" and answer.strip() == "")
    )
    mode_fields_correct = (
        (expected_action == "WAIT" and answer_mode == "NONE" and not answer.strip())
        or (
            expected_action == "RESPOND"
            and (
                (answer_mode == "FAST" and bool(answer.strip()))
                or (answer_mode == "THINK" and not answer.strip())
            )
        )
    )
    leak_free = not any(
        marker in (raw_text + answer)
        for marker in ("<think>", "</think>", "Self-Correction", "Verification")
    )

    return {
        "id": case["id"],
        "expected_action": expected_action,
        "source_expected_action": case["expected_action"],
        "actual_action": action,
        "answer_mode": answer_mode,
        "action_correct": action_correct,
        "question_terms_correct": not missing_terms,
        "missing_question_terms": missing_terms,
        "wait_fields_correct": wait_fields_correct,
        "mode_fields_correct": mode_fields_correct,
        "answer_characters": len(answer),
        "answer_within_limit": expected_action == "WAIT" or len(answer) <= 160,
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
        "focus_question": question,
        "answer": answer,
        "raw_text": raw_text,
        "error": error,
    }


def main() -> int:
    load_env_file(REPO_ROOT / ".env.local")
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        print("DEEPSEEK_API_KEY is not set", file=sys.stderr)
        return 1

    cases = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    concurrency = int(os.environ.get("FOCUS_EVAL_CONCURRENCY", "4"))
    thinking_enabled = (
        os.environ.get("DEEPSEEK_FOCUS_THINKING", "enabled").lower() == "enabled"
    )
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
        results = list(
            executor.map(
                lambda case: run_case(case, api_key, thinking_enabled), cases
            )
        )

    first_text_values = [
        result["first_text_seconds"]
        for result in results
        if result["first_text_seconds"] is not None
    ]
    total_values = [result["total_seconds"] for result in results]
    passed = [
        result
        for result in results
        if result["action_correct"]
        and result["question_terms_correct"]
        and result["wait_fields_correct"]
        and result["mode_fields_correct"]
        and result["answer_within_limit"]
        and result["leak_free"]
        and result["error"] is None
    ]
    by_action: dict[str, Any] = {}
    for action in ("WAIT", "RESPOND"):
        action_results = [result for result in results if result["expected_action"] == action]
        by_action[action] = {
            "cases": len(action_results),
            "action_correct": sum(result["action_correct"] for result in action_results),
        }

    summary = {
        "model": "deepseek-v4-flash",
        "thinking": "enabled/high" if thinking_enabled else "disabled",
        "cases": len(results),
        "passed": len(passed),
        "pass_rate": len(passed) / len(results),
        "action_accuracy": sum(result["action_correct"] for result in results)
        / len(results),
        "json_errors": sum(result["error"] is not None for result in results),
        "thinking_leaks": sum(not result["leak_free"] for result in results),
        "answer_limit_failures": sum(
            not result["answer_within_limit"] for result in results
        ),
        "by_action": by_action,
        "first_text_seconds": {
            "average": statistics.fmean(first_text_values),
            "p50": statistics.median(first_text_values),
            "p95": percentile(first_text_values, 0.95),
            "max": max(first_text_values),
        },
        "total_seconds": {
            "average": statistics.fmean(total_values),
            "p50": statistics.median(total_values),
            "p95": percentile(total_values, 0.95),
            "max": max(total_values),
        },
    }
    print(json.dumps({"summary": summary, "results": results}, ensure_ascii=False, indent=2))
    return 0 if len(passed) == len(results) else 2


if __name__ == "__main__":
    raise SystemExit(main())
