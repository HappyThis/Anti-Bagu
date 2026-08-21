from anti_bagu.llm.deepseek import FOCUS_SYSTEM_PROMPT


def test_focus_prompt_prioritizes_latest_interviewer_topic_switch() -> None:
    assert "始终优先检查时间上最新的 I 发言" in FOCUS_SYSTEM_PROMPT
    assert "切换了技术名词、考察对象或话题" in FOCUS_SYSTEM_PROMPT
    assert "不得因为旧话题仍在上下文中而返回 WAIT" in FOCUS_SYSTEM_PROMPT


def test_focus_prompt_treats_colloquial_interview_checks_as_questions() -> None:
    for phrase in ("了解 XXX", "知道 XXX 吗", "用过 XXX 吗", "熟悉 XXX 吗"):
        assert phrase in FOCUS_SYSTEM_PROMPT
    assert "不确定是新问题还是普通陈述时，优先 RESPOND" in FOCUS_SYSTEM_PROMPT


def test_focus_prompt_forbids_cross_topic_question_fusion() -> None:
    assert "最小相关上下文" in FOCUS_SYSTEM_PROMPT
    assert "视为话题硬边界" in FOCUS_SYSTEM_PROMPT
    assert "禁止把旧话题拼入 focus_question 或 answer" in FOCUS_SYSTEM_PROMPT
    assert "不得合并此前无关的 Redis 问题" in FOCUS_SYSTEM_PROMPT


def test_fast_answer_prompt_requires_scan_friendly_short_lines() -> None:
    assert "适合候选人在 3 秒内扫读" in FOCUS_SYSTEM_PROMPT
    assert "总共 3–5 行" in FOCUS_SYSTEM_PROMPT
    assert "第一行以“核心：”直接给结论" in FOCUS_SYSTEM_PROMPT
    assert "禁止写成长段" in FOCUS_SYSTEM_PROMPT
