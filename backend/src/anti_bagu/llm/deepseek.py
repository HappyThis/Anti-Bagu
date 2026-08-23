from __future__ import annotations

import base64
from typing import Any

from openai import AsyncOpenAI

from anti_bagu.interview.events import ModelResult, parse_model_result_json
from anti_bagu.llm.prompts import INTERVIEW_SYSTEM_PROMPT, SCREENSHOT_INPUT_NOTE


class DeepSeekInterviewResponder:
    def __init__(self, api_key: str, base_url: str, model: str) -> None:
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        self._model = model

    async def respond(
        self,
        *,
        prompt: str,
        image_data: bytes | None = None,
        mime_type: str | None = None,
    ) -> ModelResult:
        has_image = image_data is not None
        user_content: str | list[dict[str, Any]]
        if has_image:
            encoded = base64.b64encode(image_data).decode("ascii")
            user_content = [
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{mime_type or 'image/jpeg'};base64,{encoded}",
                    },
                },
                {
                    "type": "text",
                    "text": SCREENSHOT_INPUT_NOTE,
                },
            ]
        else:
            user_content = prompt

        request: dict[str, Any] = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": INTERVIEW_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            "response_format": {"type": "json_object"},
            "max_tokens": 6_000,
            "temperature": 0.1,
            "extra_body": {"thinking": {"type": "disabled"}},
        }

        response = await self._client.chat.completions.create(**request)
        return parse_model_result_json(response.choices[0].message.content or "")

    async def close(self) -> None:
        await self._client.close()


class UnavailableInterviewResponder:
    async def respond(
        self,
        *,
        prompt: str,
        image_data: bytes | None = None,
        mime_type: str | None = None,
    ) -> ModelResult:
        del prompt, image_data, mime_type
        raise RuntimeError("DEEPSEEK_API_KEY is not configured")
