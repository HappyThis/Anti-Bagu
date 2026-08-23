from anti_bagu.llm.prompts import INTERVIEW_SYSTEM_PROMPT


def test_single_prompt_prioritizes_latest_interviewer_question() -> None:
    assert "始终优先处理最新的 I 发言" in INTERVIEW_SYSTEM_PROMPT
    assert "只回答新问题" in INTERVIEW_SYSTEM_PROMPT
    assert "历史 Q/A 只用于理解上下文" in INTERVIEW_SYSTEM_PROMPT


def test_single_prompt_handles_text_and_screenshot_coding() -> None:
    assert "输入可能包含截图" in INTERVIEW_SYSTEM_PROMPT
    assert "截图与语音使用相同的回答规则" in INTERVIEW_SYSTEM_PROMPT
    assert "算法题必须返回完整 code" in INTERVIEW_SYSTEM_PROMPT
    assert "默认使用 Python" in INTERVIEW_SYSTEM_PROMPT


def test_single_prompt_only_allows_wait_or_answer_json() -> None:
    assert '{"type":"wait"}' in INTERVIEW_SYSTEM_PROMPT
    assert '"type":"answer"' in INTERVIEW_SYSTEM_PROMPT
    assert "每次只能返回一个合法 JSON 对象" in INTERVIEW_SYSTEM_PROMPT
