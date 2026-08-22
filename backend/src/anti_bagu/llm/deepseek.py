from __future__ import annotations

import json
from collections.abc import AsyncIterator
from pathlib import Path

from openai import AsyncOpenAI

from anti_bagu.interview.events import FocusResult

PROMPT_DIR = Path(__file__).resolve().parent / "prompts"
FOCUS_SYSTEM_PROMPT = (PROMPT_DIR / "focus_responder.txt").read_text(
    encoding="utf-8"
).strip()


class DeepSeekFocusResponder:
    def __init__(self, api_key: str, base_url: str, model: str) -> None:
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        self._model = model
        self._prompt = FOCUS_SYSTEM_PROMPT

    async def respond(self, *, prompt: str) -> FocusResult:
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": self._prompt},
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
            max_tokens=1000,
            temperature=0.1,
            extra_body={"thinking": {"type": "disabled"}},
        )
        content = response.choices[0].message.content or "{}"
        return FocusResult.model_validate_json(content)

    async def close(self) -> None:
        await self._client.close()


class DeepSeekThinkingAnswerer:
    def __init__(self, api_key: str, base_url: str, model: str) -> None:
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        self._model = model
        self._prompt = (PROMPT_DIR / "thinking_answer.txt").read_text(encoding="utf-8")

    async def stream_answer(
        self,
        *,
        question: str,
        conversation: list[dict[str, str]],
    ) -> AsyncIterator[str]:
        payload = {"question": question, "conversation": conversation}
        stream = await self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": self._prompt},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            stream=True,
            max_tokens=3000,
            reasoning_effort="high",
            extra_body={"thinking": {"type": "enabled"}},
        )
        try:
            async for chunk in stream:
                if not chunk.choices:
                    continue
                content = chunk.choices[0].delta.content
                if content:
                    yield content
        finally:
            await stream.close()

    async def close(self) -> None:
        await self._client.close()


class UnavailableFocusResponder:
    async def respond(self, *, prompt: str) -> FocusResult:
        del prompt
        raise RuntimeError("DEEPSEEK_API_KEY is not configured")


class UnavailableThinkingAnswerer:
    async def stream_answer(
        self,
        *,
        question: str,
        conversation: list[dict[str, str]],
    ) -> AsyncIterator[str]:
        del question, conversation
        if False:
            yield ""
        raise RuntimeError("DEEPSEEK_API_KEY is not configured")
