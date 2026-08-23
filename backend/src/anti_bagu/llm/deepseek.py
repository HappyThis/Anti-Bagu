from __future__ import annotations

import base64
import json
from typing import Any

from openai import AsyncOpenAI
from pydantic import ValidationError

from anti_bagu.interview.events import ModelResult, parse_model_result_json
from anti_bagu.llm.base import (
    InterviewResponse,
    ModelOutputFailure,
    ModelOutputRetriesExhausted,
)
from anti_bagu.llm.prompts import (
    INTERVIEW_SYSTEM_PROMPT,
    MODEL_OUTPUT_RETRY_NOTE,
    SCREENSHOT_INPUT_NOTE,
)


class InvalidModelOutput(ValueError):
    pass


class DeepSeekInterviewResponder:
    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        *,
        client: AsyncOpenAI | None = None,
    ) -> None:
        self._client = client or AsyncOpenAI(api_key=api_key, base_url=base_url)
        self._model = model

    async def respond(
        self,
        *,
        prompt: str,
        image_data: bytes | None = None,
        mime_type: str | None = None,
    ) -> InterviewResponse:
        has_image = image_data is not None
        encoded = base64.b64encode(image_data).decode("ascii") if has_image else ""
        failures: list[ModelOutputFailure] = []
        for attempt in (1, 2):
            retry_note = (
                MODEL_OUTPUT_RETRY_NOTE.format(error=failures[-1].error_message)
                if failures
                else ""
            )
            user_content = self._user_content(
                prompt=prompt,
                has_image=has_image,
                encoded_image=encoded,
                mime_type=mime_type,
                retry_note=retry_note,
            )
            request: dict[str, Any] = {
                "model": self._model,
                "messages": [
                    {"role": "system", "content": INTERVIEW_SYSTEM_PROMPT},
                    {"role": "user", "content": user_content},
                ],
                "response_format": {"type": "json_object"},
                "max_tokens": 6_000,
                "temperature": 0.1 if attempt == 1 else 0,
                "extra_body": {"thinking": {"type": "disabled"}},
            }
            response = await self._client.chat.completions.create(**request)
            choice = response.choices[0]
            content = choice.message.content or ""
            finish_reason = str(choice.finish_reason) if choice.finish_reason else None
            try:
                result = self._parse(content, finish_reason)
            except (json.JSONDecodeError, ValidationError, InvalidModelOutput) as exc:
                failures.append(
                    ModelOutputFailure(
                        attempt=attempt,
                        raw_content=content,
                        finish_reason=finish_reason,
                        error_type=type(exc).__name__,
                        error_message=str(exc)[:500],
                    )
                )
                continue
            return InterviewResponse(result=result, output_failures=tuple(failures))
        raise ModelOutputRetriesExhausted(tuple(failures))

    @staticmethod
    def _parse(content: str, finish_reason: str | None) -> ModelResult:
        if not content.strip():
            raise InvalidModelOutput("model returned empty content")
        if finish_reason == "length":
            raise InvalidModelOutput("model output was truncated: finish_reason=length")
        return parse_model_result_json(content)

    @staticmethod
    def _user_content(
        *,
        prompt: str,
        has_image: bool,
        encoded_image: str,
        mime_type: str | None,
        retry_note: str,
    ) -> str | list[dict[str, Any]]:
        if not has_image:
            return f"{prompt}\n\n{retry_note}" if retry_note else prompt
        instruction = (
            f"{SCREENSHOT_INPUT_NOTE}\n\n{retry_note}"
            if retry_note
            else SCREENSHOT_INPUT_NOTE
        )
        return [
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:{mime_type or 'image/jpeg'};base64,{encoded_image}",
                },
            },
            {"type": "text", "text": instruction},
        ]

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
