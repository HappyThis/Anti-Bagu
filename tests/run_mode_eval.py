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
CASES_PATH = REPO_ROOT / "tests" / "fixtures" / "mode_cases.json"
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


def run_case(case: dict[str, Any], api_key: str) -> dict[str, Any]:
    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
    payload = {
        "current_focus": None,
        "conversation": [{"speaker": "interviewer", "text": case["question"]}],
    }
    started_at = time.perf_counter()
    first_text_at: float | None = None
    chunks: list[str] = []
    error = None
    try:
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
            if content:
                if first_text_at is None:
                    first_text_at = time.perf_counter()
                chunks.append(content)
        parsed = json.loads("".join(chunks))
    except Exception as exc:
        parsed = {}
        error = f"{type(exc).__name__}: {exc}"
    completed_at = time.perf_counter()

    actual_mode = str(parsed.get("answer_mode", "")).upper()
    answer = str(parsed.get("answer", ""))
    expected_mode = case["expected_mode"]
    fields_correct = (
        (actual_mode == "FAST" and bool(answer.strip()))
        or (actual_mode == "THINK" and not answer.strip())
    )
    return {
        "id": case["id"],
        "expected_mode": expected_mode,
        "actual_mode": actual_mode,
        "mode_correct": actual_mode == expected_mode,
        "fields_correct": fields_correct,
        "focus_question": parsed.get("focus_question", ""),
        "answer": answer,
        "first_text_seconds": first_text_at - started_at if first_text_at else None,
        "total_seconds": completed_at - started_at,
        "error": error,
    }


def main() -> int:
    load_env_file(REPO_ROOT / ".env.local")
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        print("DEEPSEEK_API_KEY is not set", file=sys.stderr)
        return 1
    cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    concurrency = int(os.environ.get("MODE_EVAL_CONCURRENCY", "4"))
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
        results = list(executor.map(lambda case: run_case(case, api_key), cases))

    latencies = [result["first_text_seconds"] for result in results if result["first_text_seconds"]]
    summary = {
        "cases": len(results),
        "correct": sum(result["mode_correct"] for result in results),
        "accuracy": sum(result["mode_correct"] for result in results) / len(results),
        "field_errors": sum(not result["fields_correct"] for result in results),
        "json_errors": sum(result["error"] is not None for result in results),
        "first_text_seconds": {
            "average": statistics.fmean(latencies),
            "p50": statistics.median(latencies),
            "p95": percentile(latencies, 0.95),
            "max": max(latencies),
        },
    }
    print(json.dumps({"summary": summary, "results": results}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
