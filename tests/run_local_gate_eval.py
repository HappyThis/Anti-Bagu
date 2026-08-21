#!/usr/bin/env python3

from __future__ import annotations

import json
from pathlib import Path

from local_route_gate import requires_thinking


ROOT = Path(__file__).resolve().parent.parent
CASES = ROOT / "tests" / "fixtures" / "mode_cases.json"


def main() -> int:
    cases = json.loads(CASES.read_text(encoding="utf-8"))
    results = []
    for case in cases:
        actual = "THINK" if requires_thinking(case["question"]) else "FAST"
        results.append(
            {
                "id": case["id"],
                "expected": case["expected_mode"],
                "actual": actual,
                "correct": actual == case["expected_mode"],
            }
        )
    correct = sum(result["correct"] for result in results)
    print(
        json.dumps(
            {
                "summary": {
                    "cases": len(results),
                    "correct": correct,
                    "accuracy": correct / len(results),
                },
                "results": results,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
