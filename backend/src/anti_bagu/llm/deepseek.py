from __future__ import annotations

import base64
from pathlib import Path

from openai import AsyncOpenAI

from anti_bagu.interview.events import ModelResult, parse_model_result_json

PROMPT_DIR = Path(__file__).resolve().parent / "prompts"
FOCUS_SYSTEM_PROMPT = (PROMPT_DIR / "focus_responder.txt").read_text(
    encoding="utf-8"
).strip()
SCREENSHOT_SYSTEM_PROMPT = (PROMPT_DIR / "screenshot_answer.txt").read_text(
    encoding="utf-8"
).strip()


class DeepSeekFocusResponder:
    def __init__(self, api_key: str, base_url: str, model: str) -> None:
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        self._model = model
        self._prompt = FOCUS_SYSTEM_PROMPT

    async def respond(self, *, prompt: str) -> ModelResult:
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": self._prompt},
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
            max_tokens=6000,
            temperature=0.1,
            extra_body={"thinking": {"type": "disabled"}},
        )
        content = response.choices[0].message.content or "{}"
        return parse_model_result_json(content)

    async def close(self) -> None:
        await self._client.close()


class DeepSeekScreenshotAnalyzer:
    def __init__(self, api_key: str, base_url: str, model: str) -> None:
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        self._model = model
        self._prompt = SCREENSHOT_SYSTEM_PROMPT

    async def analyze(
        self,
        *,
        prompt: str,
        image_data: bytes,
        mime_type: str,
    ) -> ModelResult:
        encoded = base64.b64encode(image_data).decode("ascii")
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": self._prompt},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{mime_type};base64,{encoded}",
                            },
                        },
                    ],
                },
            ],
            response_format={"type": "json_object"},
            max_tokens=6000,
            reasoning_effort="high",
            extra_body={"thinking": {"type": "enabled"}},
        )
        content = response.choices[0].message.content or "{}"
        return parse_model_result_json(content)

    async def close(self) -> None:
        await self._client.close()


class UnavailableFocusResponder:
    async def respond(self, *, prompt: str) -> ModelResult:
        del prompt
        raise RuntimeError("DEEPSEEK_API_KEY is not configured")


class UnavailableScreenshotAnalyzer:
    async def analyze(
        self,
        *,
        prompt: str,
        image_data: bytes,
        mime_type: str,
    ) -> ModelResult:
        del prompt, image_data, mime_type
        raise RuntimeError("DEEPSEEK_API_KEY is not configured")
