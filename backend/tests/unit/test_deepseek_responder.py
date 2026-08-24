from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from anti_bagu.interview.events import AnswerResult
from anti_bagu.llm.base import InterviewResponse, ModelOutputRetriesExhausted
from anti_bagu.llm.deepseek import DeepSeekInterviewResponder


class FakeCompletions:
    def __init__(self, responses: list[object]) -> None:
        self.responses = responses
        self.calls: list[dict[str, object]] = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        value = self.responses.pop(0)
        if isinstance(value, Exception):
            raise value
        return value


class FakeClient:
    def __init__(self, responses: list[object]) -> None:
        self.completions = FakeCompletions(responses)
        self.chat = SimpleNamespace(completions=self.completions)

    async def close(self) -> None:
        return None


def response(content: str, finish_reason: str = "stop"):
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=content),
                finish_reason=finish_reason,
            )
        ]
    )


def valid_answer() -> str:
    return json.dumps(
        {
            "type": "answer",
            "question": "Redis 为什么快？",
            "answer": "因为内存和 I/O 多路复用。",
        },
        ensure_ascii=False,
    )


@pytest.mark.asyncio
async def test_invalid_json_is_reported_to_model_and_retried_once() -> None:
    client = FakeClient([response(f"{valid_answer()}\n额外解释"), response(valid_answer())])
    subject = DeepSeekInterviewResponder(
        "key", "https://example.com", "model", client=client
    )

    result = await subject.respond(prompt="# 新增对话\n- I: Redis 为什么快？")

    assert isinstance(result, InterviewResponse)
    assert isinstance(result.result, AnswerResult)
    assert len(result.output_failures) == 1
    assert result.output_failures[0].attempt == 1
    assert result.output_failures[0].error_type == "JSONDecodeError"
    assert len(client.completions.calls) == 2
    retry = client.completions.calls[1]
    assert retry["temperature"] == 0
    retry_content = retry["messages"][1]["content"]
    assert "Extra data" in retry_content
    assert "只输出一个合法 json 对象" in retry_content


@pytest.mark.asyncio
async def test_image_retry_resends_same_image_with_format_feedback() -> None:
    client = FakeClient([response(""), response(valid_answer())])
    subject = DeepSeekInterviewResponder(
        "key", "https://example.com", "model", client=client
    )

    result = await subject.respond(
        prompt="ignored for image",
        image_data=b"image",
        mime_type="image/jpeg",
        selection_hint="第 2 个问题：事务与并发控制",
    )

    assert isinstance(result, InterviewResponse)
    first_content = client.completions.calls[0]["messages"][1]["content"]
    retry_content = client.completions.calls[1]["messages"][1]["content"]
    assert first_content[0]["image_url"] == retry_content[0]["image_url"]
    assert "empty content" in retry_content[1]["text"]
    assert "第 2 个问题：事务与并发控制" in retry_content[1]["text"]


@pytest.mark.asyncio
async def test_two_invalid_outputs_raise_terminal_format_error() -> None:
    client = FakeClient([response("not json"), response("still not json")])
    subject = DeepSeekInterviewResponder(
        "key", "https://example.com", "model", client=client
    )

    with pytest.raises(ModelOutputRetriesExhausted) as raised:
        await subject.respond(prompt="question")

    assert len(raised.value.failures) == 2
    assert [failure.attempt for failure in raised.value.failures] == [1, 2]
    assert len(client.completions.calls) == 2


@pytest.mark.asyncio
async def test_non_format_api_error_is_not_retried() -> None:
    client = FakeClient([RuntimeError("network failed")])
    subject = DeepSeekInterviewResponder(
        "key", "https://example.com", "model", client=client
    )

    with pytest.raises(RuntimeError, match="network failed"):
        await subject.respond(prompt="question")

    assert len(client.completions.calls) == 1
