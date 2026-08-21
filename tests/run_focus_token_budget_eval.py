#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import random
import statistics
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from openai import OpenAI


REPO_ROOT = Path(__file__).resolve().parent.parent
PROMPT_PATH = REPO_ROOT / "tests" / "fixtures" / "focus_token_budget_prompt.txt"
SYSTEM_PROMPT = PROMPT_PATH.read_text(encoding="utf-8").strip()
DEFAULT_BUCKETS = (1_000, 2_000, 4_000, 8_000, 16_000, 32_000, 64_000, 128_000)
DEFAULT_POSITIONS = ("middle",)
POSITION_FRACTIONS = {"early": 0.1, "middle": 0.5, "late": 0.9}


@dataclass(frozen=True, slots=True)
class Scenario:
    id: str
    previous_question: str
    previous_answer: str
    critical_lines: tuple[str, ...]
    recall_line: str
    expected_action: str
    expected_mode: str
    required_terms: tuple[str, ...]


SCENARIOS = {
    "mysql_new": Scenario(
        id="mysql_new",
        previous_question="请解释缓存穿透、击穿和雪崩。",
        previous_answer="穿透是查询不存在的数据，击穿是热点缓存失效，雪崩是大量缓存同时失效。",
        critical_lines=(
            "- I: 我们现在切换到数据库问题。",
            "- I: 在 MySQL 中，如何定位慢查询？",
        ),
        recall_line="- I: 请回答我刚才提出的核心技术问题。",
        expected_action="RESPOND",
        expected_mode="FAST",
        required_terms=("mysql", "慢查询"),
    ),
    "redis_followup": Scenario(
        id="redis_followup",
        previous_question="Redis 为什么快？",
        previous_answer="Redis 快主要因为内存、单线程、I/O 多路复用和高效数据结构。",
        critical_lines=(
            "- C: 我刚才主要回答了内存和单线程。",
            "- I: 那 Redis 的 I/O 模型为什么高效？",
        ),
        recall_line="- I: 请继续回答刚才的追问。",
        expected_action="RESPOND",
        expected_mode="FAST",
        required_terms=("redis", "i/o"),
    ),
    "jvm_new": Scenario(
        id="jvm_new",
        previous_question="Java 线程池有哪些核心参数？",
        previous_answer="核心线程数、最大线程数、存活时间、任务队列、线程工厂和拒绝策略。",
        critical_lines=(
            "- I: 我们换一个问题。",
            "- I: JVM 如何判断对象是否可以被回收？",
        ),
        recall_line="- I: 请回答刚才新的技术问题。",
        expected_action="RESPOND",
        expected_mode="FAST",
        required_terms=("jvm", "回收"),
    ),
    "wait_background": Scenario(
        id="wait_background",
        previous_question="MySQL 索引为什么使用 B+ 树？",
        previous_answer="B+ 树扇出高、树高低，适合磁盘访问和范围查询。",
        critical_lines=(
            "- I: 我先补充一下项目背景。",
            "- C: 好的。",
            "- I: 你先别回答，我还没有把背景讲完。",
        ),
        recall_line="- I: 这里仍然只是背景说明。",
        expected_action="WAIT",
        expected_mode="NONE",
        required_terms=(),
    ),
    "think_design": Scenario(
        id="think_design",
        previous_question="常见的限流算法有哪些？",
        previous_answer="固定窗口、滑动窗口、漏桶和令牌桶。",
        critical_lines=(
            "- I: 现在做一道系统设计题。",
            "- I: 请设计一个支持每秒十万请求的分布式限流器，并说明一致性和容灾方案。",
        ),
        recall_line="- I: 请按刚才的约束完成设计。",
        expected_action="RESPOND",
        expected_mode="THINK",
        required_terms=("限流",),
    ),
}


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def parse_csv_ints(value: str) -> tuple[int, ...]:
    return tuple(int(item.strip()) for item in value.split(",") if item.strip())


def parse_csv_strings(value: str) -> tuple[str, ...]:
    positions = tuple(item.strip() for item in value.split(",") if item.strip())
    invalid = [position for position in positions if position not in POSITION_FRACTIONS]
    if invalid:
        raise ValueError(f"invalid positions: {invalid}")
    return positions


SUBJECTS = (
    "项目团队",
    "研发流程",
    "日常协作",
    "发布过程",
    "故障复盘",
    "需求评审",
    "测试阶段",
    "监控体系",
    "代码审查",
    "容量规划",
)
ACTIONS = (
    "会记录背景信息并确认业务范围",
    "通常按照既定流程整理相关材料",
    "会结合历史经验补充必要说明",
    "需要关注团队之间的信息同步",
    "会提前梳理已有约束和实施步骤",
    "通常先明确目标再安排后续工作",
    "会保留过程记录方便后续复盘",
    "需要根据业务节奏持续调整计划",
    "会将不同阶段的结果统一归档",
    "通常通过协作机制推进日常任务",
)
CONTEXTS = (
    "这段内容只是普通项目背景",
    "这里没有提出新的技术问题",
    "这部分用于说明日常工作方式",
    "这些信息与当前技术问题无直接关系",
    "这一段仅用于补充非技术上下文",
)


def filler_line(index: int) -> str:
    role = "I" if index % 3 else "C"
    subject = SUBJECTS[index % len(SUBJECTS)]
    action = ACTIONS[(index // len(SUBJECTS)) % len(ACTIONS)]
    context = CONTEXTS[(index // (len(SUBJECTS) * len(ACTIONS))) % len(CONTEXTS)]
    return f"- {role}: {subject}{action}，{context}。"


def base_prefix(scenario: Scenario) -> str:
    return (
        "# 上一焦点\n"
        f"Q: {scenario.previous_question}\n"
        f"A: {scenario.previous_answer}\n\n"
        "# 对话\n"
    )


def build_prompt_for_characters(
    target_characters: int, position: str, scenario: Scenario
) -> str:
    prefix = base_prefix(scenario)
    minimum = (
        len(SYSTEM_PROMPT)
        + len(prefix)
        + sum(map(len, scenario.critical_lines))
        + len(scenario.recall_line)
    )
    target_characters = max(target_characters, minimum)
    target_user_characters = target_characters - len(SYSTEM_PROMPT)

    filler: list[str] = []
    current_length = (
        len(prefix)
        + sum(map(len, scenario.critical_lines))
        + len(scenario.recall_line)
    )
    index = 0
    while current_length < target_user_characters:
        line = filler_line(index)
        filler.append(line)
        current_length += len(line) + 1
        index += 1

    insertion_index = round(len(filler) * POSITION_FRACTIONS[position])
    lines = [
        *filler[:insertion_index],
        *scenario.critical_lines,
        *filler[insertion_index:],
        scenario.recall_line,
    ]
    return prefix + "\n".join(lines)


@dataclass(slots=True)
class RequestResult:
    target_tokens: int
    position: str
    scenario: str
    repeat: int
    total_characters: int
    prompt_tokens: int | None
    completion_tokens: int | None
    first_text_seconds: float | None
    total_seconds: float
    action: str
    answer_mode: str
    focus_question: str
    answer: str
    success: bool
    error: str | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "target_tokens": self.target_tokens,
            "position": self.position,
            "scenario": self.scenario,
            "repeat": self.repeat,
            "total_characters": self.total_characters,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "first_text_seconds": self.first_text_seconds,
            "total_seconds": self.total_seconds,
            "action": self.action,
            "answer_mode": self.answer_mode,
            "focus_question": self.focus_question,
            "answer": self.answer,
            "success": self.success,
            "error": self.error,
        }


def parse_response(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        stripped = "\n".join(lines[1:-1])
    return json.loads(stripped)


def run_request(
    client: OpenAI,
    *,
    model: str,
    target_tokens: int,
    position: str,
    scenario: Scenario,
    repeat: int,
    characters_per_token: float,
) -> RequestResult:
    target_characters = round(target_tokens * characters_per_token)
    user_prompt = build_prompt_for_characters(
        target_characters, position, scenario
    )
    started_at = time.perf_counter()
    first_text_at: float | None = None
    chunks: list[str] = []
    usage: Any = None
    parsed: dict[str, Any] = {}
    error: str | None = None

    try:
        stream = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            stream=True,
            max_tokens=800,
            temperature=0.1,
            response_format={"type": "json_object"},
            stream_options={"include_usage": True},
            extra_body={"thinking": {"type": "disabled"}},
        )
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
            content = chunk.choices[0].delta.content
            if content:
                if first_text_at is None:
                    first_text_at = now
                chunks.append(content)
        parsed = parse_response("".join(chunks))
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"

    completed_at = time.perf_counter()
    action = str(parsed.get("action", "")).upper()
    answer_mode = str(parsed.get("answer_mode", "")).upper()
    focus_question = str(parsed.get("focus_question", ""))
    answer = str(parsed.get("answer", ""))
    normalized_question = focus_question.lower().replace(" ", "")
    terms_present = all(
        term.lower().replace(" ", "") in normalized_question
        for term in scenario.required_terms
    )
    if scenario.expected_action == "WAIT":
        success = (
            error is None
            and action == "WAIT"
            and answer_mode == "NONE"
            and not focus_question.strip()
            and not answer.strip()
        )
    else:
        success = (
            error is None
            and action == "RESPOND"
            and answer_mode == scenario.expected_mode
            and terms_present
            and (
                (answer_mode == "FAST" and bool(answer.strip()))
                or (answer_mode == "THINK" and not answer.strip())
            )
        )
    prompt_tokens = usage.get("prompt_tokens") if isinstance(usage, dict) else None
    completion_tokens = (
        usage.get("completion_tokens") if isinstance(usage, dict) else None
    )
    return RequestResult(
        target_tokens=target_tokens,
        position=position,
        scenario=scenario.id,
        repeat=repeat,
        total_characters=len(SYSTEM_PROMPT) + len(user_prompt),
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        first_text_seconds=(
            first_text_at - started_at if first_text_at is not None else None
        ),
        total_seconds=completed_at - started_at,
        action=action,
        answer_mode=answer_mode,
        focus_question=focus_question,
        answer=answer,
        success=success,
        error=error,
    )


def summarize(results: list[RequestResult]) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for target in sorted({result.target_tokens for result in results}):
        selected = [result for result in results if result.target_tokens == target]
        actual_tokens = [
            result.prompt_tokens for result in selected if result.prompt_tokens is not None
        ]
        first_text = [
            result.first_text_seconds
            for result in selected
            if result.first_text_seconds is not None
        ]
        total = [result.total_seconds for result in selected]
        summaries.append(
            {
                "target_tokens": target,
                "requests": len(selected),
                "successes": sum(result.success for result in selected),
                "success_rate": sum(result.success for result in selected)
                / len(selected),
                "actual_prompt_tokens": {
                    "min": min(actual_tokens) if actual_tokens else None,
                    "median": statistics.median(actual_tokens) if actual_tokens else None,
                    "max": max(actual_tokens) if actual_tokens else None,
                },
                "first_text_seconds": {
                    "median": statistics.median(first_text) if first_text else None,
                    "max": max(first_text) if first_text else None,
                },
                "total_seconds": {
                    "median": statistics.median(total),
                    "max": max(total),
                },
                "errors": sum(result.error is not None for result in selected),
            }
        )
    return summaries


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--buckets",
        default=",".join(str(value) for value in DEFAULT_BUCKETS),
    )
    parser.add_argument("--positions", default=",".join(DEFAULT_POSITIONS))
    parser.add_argument("--scenarios", default="mysql_new")
    parser.add_argument("--seed", type=int, default=20260821)
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--initial-characters-per-token", type=float, default=1.6)
    args = parser.parse_args()

    load_env_file(REPO_ROOT / ".env.local")
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        print("DEEPSEEK_API_KEY is not set", file=sys.stderr)
        return 1
    model = os.environ.get("ANTIBAGU_MODEL_NAME", "deepseek-v4-flash")
    buckets = parse_csv_ints(args.buckets)
    positions = parse_csv_strings(args.positions)
    scenario_ids = tuple(
        item.strip() for item in args.scenarios.split(",") if item.strip()
    )
    invalid_scenarios = [item for item in scenario_ids if item not in SCENARIOS]
    if invalid_scenarios:
        raise ValueError(f"invalid scenarios: {invalid_scenarios}")
    client = OpenAI(
        api_key=api_key,
        base_url=os.environ.get("ANTIBAGU_MODEL_BASE_URL", "https://api.deepseek.com"),
        timeout=180,
    )

    warmup = run_request(
        client,
        model=model,
        target_tokens=1_000,
        position="late",
        scenario=SCENARIOS["mysql_new"],
        repeat=0,
        characters_per_token=args.initial_characters_per_token,
    )
    if warmup.prompt_tokens:
        calibrated_ratio = warmup.total_characters / warmup.prompt_tokens
    else:
        calibrated_ratio = args.initial_characters_per_token
    print(
        json.dumps(
            {
                "event": "calibrated",
                "characters_per_token": calibrated_ratio,
                "warmup": warmup.as_dict(),
            },
            ensure_ascii=False,
        ),
        file=sys.stderr,
        flush=True,
    )

    tasks = [
        (bucket, position, SCENARIOS[scenario_id], repeat)
        for bucket in buckets
        for position in positions
        for scenario_id in scenario_ids
        for repeat in range(1, args.repeats + 1)
    ]
    random.Random(args.seed).shuffle(tasks)
    results: list[RequestResult] = []
    for index, (bucket, position, scenario, repeat) in enumerate(tasks, start=1):
        result = run_request(
            client,
            model=model,
            target_tokens=bucket,
            position=position,
            scenario=scenario,
            repeat=repeat,
            characters_per_token=calibrated_ratio,
        )
        results.append(result)
        print(
            json.dumps(
                {
                    "event": "request_complete",
                    "index": index,
                    "total": len(tasks),
                    **result.as_dict(),
                },
                ensure_ascii=False,
            ),
            file=sys.stderr,
            flush=True,
        )

    output = {
        "config": {
            "model": model,
            "buckets": buckets,
            "positions": positions,
            "scenarios": scenario_ids,
            "seed": args.seed,
            "repeats": args.repeats,
            "characters_per_token": calibrated_ratio,
            "system_prompt_characters": len(SYSTEM_PROMPT),
        },
        "summaries": summarize(results),
        "results": [result.as_dict() for result in results],
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0 if all(result.success for result in results) else 2


if __name__ == "__main__":
    raise SystemExit(main())
