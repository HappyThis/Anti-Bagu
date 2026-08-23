from __future__ import annotations

from anti_bagu.interview.context import FocusPromptBuilder, TokenEstimator
from anti_bagu.interview.events import (
    Channel,
    CommittedFocus,
    ConversationTurn,
)

SYSTEM_PROMPT = "I 表示面试官，C 表示候选人。仅返回 JSON。"


def turn(
    turn_id: int,
    channel: Channel,
    text: str,
    *,
    created_at: float | None = None,
) -> ConversationTurn:
    return ConversationTurn(
        turn_id=turn_id,
        channel=channel,
        text=text,
        event_id=f"event-{turn_id}",
        created_at=float(turn_id) if created_at is None else created_at,
    )


def focus(
    index: int,
    question: str,
    answer: str,
    source_end_turn_id: int,
    *,
    code: str | None = None,
) -> CommittedFocus:
    return CommittedFocus(
        focus_id=f"focus-{index}",
        question=question,
        recommended_answer=answer,
        code=code,
        source_start_turn_id=max(1, source_end_turn_id - 1),
        source_end_turn_id=source_end_turn_id,
        created_at=float(index),
    )


def test_prompt_is_minimal_markdown_with_time_ordered_roles() -> None:
    builder = FocusPromptBuilder(system_prompt=SYSTEM_PROMPT)
    result = builder.build(
        focuses=(),
        turns=(
            turn(1, Channel.INTERVIEWER, "在 MySQL 中。"),
            turn(2, Channel.CANDIDATE, "我会先查看日志。"),
            turn(3, Channel.INTERVIEWER, "如何定位慢查询？"),
        ),
    )

    assert result.markdown == (
        "# 历史分析结果\n无\n\n# 上次分析后新增的对话\n"
        "- I: 在 MySQL 中。\n"
        "- C: 我会先查看日志。\n"
        "- I（最新）: 如何定位慢查询？"
    )
    assert "turn_id" not in result.markdown
    assert result.included_turn_ids == (1, 2, 3)


def test_noise_is_removed_and_same_role_fragments_are_merged() -> None:
    builder = FocusPromptBuilder(system_prompt=SYSTEM_PROMPT)
    result = builder.build(
        focuses=(),
        turns=(
            turn(1, Channel.CANDIDATE, "咳。"),
            turn(2, Channel.INTERVIEWER, "在 MySQL 中。"),
            turn(3, Channel.INTERVIEWER, "如何定位慢查询？"),
        ),
    )

    assert "咳" not in result.markdown
    assert "- I（最新）: 在 MySQL 中。如何定位慢查询？" in result.markdown
    assert result.removed_noise_turns == 1


def test_latest_interviewer_is_marked_even_when_candidate_speaks_afterward() -> None:
    builder = FocusPromptBuilder(system_prompt=SYSTEM_PROMPT)
    result = builder.build(
        focuses=(),
        turns=(
            turn(1, Channel.INTERVIEWER, "知道 LangChain 吗？"),
            turn(2, Channel.CANDIDATE, "用过一点。"),
        ),
    )

    assert "- I（最新）: 知道 LangChain 吗？" in result.markdown
    assert result.markdown.endswith("- C: 用过一点。")


def test_same_role_questions_do_not_merge_across_completed_focus() -> None:
    builder = FocusPromptBuilder(system_prompt=SYSTEM_PROMPT)
    result = builder.build(
        focuses=(focus(1, "Redis 为什么快？", "因为内存。", 1),),
        turns=(
            turn(1, Channel.INTERVIEWER, "Redis 为什么快？"),
            turn(2, Channel.INTERVIEWER, "知道 LangChain 吗？"),
        ),
    )

    assert "- I: Redis 为什么快？" in result.markdown
    assert "- I（最新）: 知道 LangChain 吗？" in result.markdown
    assert "Redis 为什么快？知道 LangChain" not in result.markdown


def test_same_role_questions_do_not_merge_after_long_silence() -> None:
    builder = FocusPromptBuilder(system_prompt=SYSTEM_PROMPT)
    result = builder.build(
        focuses=(),
        turns=(
            turn(1, Channel.INTERVIEWER, "Redis 为什么快？", created_at=1.0),
            turn(2, Channel.INTERVIEWER, "知道 LangChain 吗？", created_at=10.0),
        ),
    )

    assert "- I: Redis 为什么快？" in result.markdown
    assert "- I（最新）: 知道 LangChain 吗？" in result.markdown


def test_multiple_old_focuses_fill_space_before_dialogue_window() -> None:
    builder = FocusPromptBuilder(system_prompt=SYSTEM_PROMPT)
    result = builder.build(
        focuses=(
            focus(1, "Redis 为什么快？", "因为内存和 I/O 多路复用。", 2),
            focus(2, "RDB 和 AOF 有什么区别？", "一个是快照，一个是日志。", 4),
        ),
        turns=(
            turn(5, Channel.CANDIDATE, "AOF 更关注数据安全。"),
            turn(6, Channel.INTERVIEWER, "那重写机制呢？"),
        ),
    )

    assert "Redis 为什么快" in result.markdown
    assert "RDB 和 AOF" in result.markdown
    assert result.included_focus_ids == ("focus-1", "focus-2")


def test_latest_focus_is_kept_to_preserve_unspoken_recommendation() -> None:
    builder = FocusPromptBuilder(system_prompt=SYSTEM_PROMPT)
    result = builder.build(
        focuses=(
            focus(1, "Redis 为什么快？", "因为内存。", 2),
        ),
        turns=(
            turn(1, Channel.INTERVIEWER, "Redis 为什么快？"),
            turn(2, Channel.CANDIDATE, "因为内存。"),
            turn(3, Channel.INTERVIEWER, "还有呢？"),
        ),
    )

    assert result.included_focus_ids == ("focus-1",)
    assert "A: 因为内存。" in result.markdown


def test_only_turns_after_last_analysis_are_rendered_as_new_dialogue() -> None:
    builder = FocusPromptBuilder(system_prompt=SYSTEM_PROMPT)
    result = builder.build(
        focuses=(focus(1, "Redis 为什么快？", "因为内存。", 2),),
        turns=(
            turn(1, Channel.INTERVIEWER, "Redis 为什么快？"),
            turn(2, Channel.CANDIDATE, "因为内存。"),
            turn(3, Channel.CANDIDATE, "我还会补充 I/O 多路复用。"),
            turn(4, Channel.INTERVIEWER, "那单线程为什么能处理高并发？"),
        ),
        after_turn_id=2,
    )

    assert result.analysis_after_turn_id == 2
    assert result.included_turn_ids == (3, 4)
    assert "Q: Redis 为什么快？" in result.markdown
    assert "- I: Redis 为什么快？" not in result.markdown
    assert "- C: 因为内存。" not in result.markdown
    assert "- C: 我还会补充 I/O 多路复用。" in result.markdown
    assert "- I（最新）: 那单线程为什么能处理高并发？" in result.markdown


def test_latest_coding_focus_is_carried_into_next_prompt() -> None:
    builder = FocusPromptBuilder(system_prompt=SYSTEM_PROMPT)
    latest_code = (
        "def two_sum(nums, target):\n"
        "    # 记录已访问数字的位置\n"
        "    seen = {}\n"
        "    for index, value in enumerate(nums):\n"
        "        if target - value in seen:\n"
        "            return [seen[target - value], index]\n"
        "        seen[value] = index\n"
        "    return []"
    )
    result = builder.build(
        focuses=(
            focus(
                1,
                "两数之和怎么实现？",
                "使用哈希表一次遍历。",
                2,
                code=latest_code,
            ),
        ),
        turns=(
            turn(3, Channel.CANDIDATE, "我会用哈希表。"),
            turn(4, Channel.INTERVIEWER, "为什么这样是 O(n)？"),
        ),
    )

    assert result.included_focus_ids == ("focus-1",)
    assert "Code:\n```python" in result.markdown
    assert latest_code in result.markdown
    assert result.markdown.endswith("- I（最新）: 为什么这样是 O(n)？")


def test_only_latest_focus_code_is_repeated() -> None:
    builder = FocusPromptBuilder(system_prompt=SYSTEM_PROMPT)
    result = builder.build(
        focuses=(
            focus(1, "旧题", "旧答案", 2, code="def old_solution():\n    pass"),
            focus(2, "新题", "新答案", 4, code="def new_solution():\n    pass"),
        ),
        turns=(turn(5, Channel.INTERVIEWER, "这个边界条件呢？"),),
    )

    assert "def old_solution" not in result.markdown
    assert "def new_solution" in result.markdown


def test_latest_code_uses_total_budget_before_old_dialogue() -> None:
    builder = FocusPromptBuilder(
        system_prompt=SYSTEM_PROMPT,
        target_tokens=240,
        dialogue_target_tokens=160,
        history_target_tokens=40,
        estimator=TokenEstimator(characters_per_token=1),
    )
    latest_code = "def solve():\n" + "    value += 1\n" * 5
    result = builder.build(
        focuses=(
            focus(1, "如何实现？", "遍历并累计。", 2, code=latest_code),
        ),
        turns=tuple(
            turn(
                index,
                Channel.INTERVIEWER if index % 2 else Channel.CANDIDATE,
                f"较早的对话内容第{index}段。",
            )
            for index in range(3, 15)
        ),
    )

    assert result.estimated_total_tokens <= 240
    assert result.included_focus_ids == ("focus-1",)
    assert latest_code in result.markdown
    assert result.included_turn_ids[-1] == 14
    assert 3 not in result.included_turn_ids


def test_prompt_never_exceeds_fixed_total_budget() -> None:
    builder = FocusPromptBuilder(
        system_prompt=SYSTEM_PROMPT,
        target_tokens=120,
        dialogue_target_tokens=80,
        history_target_tokens=30,
        estimator=TokenEstimator(characters_per_token=1),
    )
    turns = tuple(
        turn(
            index,
            Channel.INTERVIEWER if index % 2 else Channel.CANDIDATE,
            f"这是一段用于测试固定窗口的有效中文对话内容第{index}段。",
        )
        for index in range(1, 30)
    )
    result = builder.build(turns=turns, focuses=())

    assert result.estimated_total_tokens <= 120
    assert result.compacted
    assert result.through_turn_id == 29


def test_large_dialogue_uses_most_of_the_8k_window() -> None:
    builder = FocusPromptBuilder(system_prompt=SYSTEM_PROMPT)
    turns = tuple(
        turn(
            index,
            Channel.INTERVIEWER if index % 2 else Channel.CANDIDATE,
            "这是一段有意义的中文面试对话，用于验证固定上下文窗口能够尽量使用可用空间。",
        )
        for index in range(1, 1_000)
    )
    result = builder.build(turns=turns, focuses=())

    assert 7_500 <= result.estimated_total_tokens <= 8_000
    assert result.compacted
