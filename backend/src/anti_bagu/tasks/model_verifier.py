from __future__ import annotations

import time
from dataclasses import dataclass

from openai import AsyncOpenAI

from anti_bagu.asr.qwen_streaming import QwenStreamingASRSession
from anti_bagu.config import Settings
from anti_bagu.interview.events import Channel


@dataclass(frozen=True, slots=True)
class VerificationResult:
    ok: bool
    detail: str
    latency_ms: float | None


class ModelVerifier:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def verify_asr(self, api_key: str) -> VerificationResult:
        started = time.perf_counter()

        async def discard(_):
            return None

        session = QwenStreamingASRSession(
            channel=Channel.INTERVIEWER,
            api_key=api_key,
            ws_url=self._settings.dashscope_ws_url,
            model=self._settings.asr_model,
            transcript_handler=discard,
        )
        try:
            await session.start()
            latency = (time.perf_counter() - started) * 1000
            return VerificationResult(True, self._settings.asr_model, latency)
        except Exception as exc:
            return VerificationResult(False, f"ASR 连接失败：{exc}", None)
        finally:
            await session.close()

    async def verify_llm(self, api_key: str) -> VerificationResult:
        started = time.perf_counter()
        client = AsyncOpenAI(
            api_key=api_key,
            base_url=self._settings.deepseek_base_url,
            timeout=8.0,
        )
        try:
            await client.chat.completions.create(
                model=self._settings.deepseek_model,
                messages=[{"role": "user", "content": "只回复 OK"}],
                max_tokens=4,
                temperature=0,
                extra_body={"thinking": {"type": "disabled"}},
            )
            latency = (time.perf_counter() - started) * 1000
            return VerificationResult(True, self._settings.deepseek_model, latency)
        except Exception as exc:
            return VerificationResult(False, f"LLM 连接失败：{exc}", None)
        finally:
            await client.close()
