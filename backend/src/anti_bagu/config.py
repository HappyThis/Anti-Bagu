from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]


def load_local_env(path: Path | None = None) -> None:
    env_path = path or REPO_ROOT / ".env.local"
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


@dataclass(frozen=True, slots=True)
class Settings:
    host: str = "127.0.0.1"
    port: int = 8765
    deepseek_api_key: str | None = None
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-v4-flash"
    dashscope_api_key: str | None = None
    dashscope_ws_url: str = "wss://dashscope.aliyuncs.com/api-ws/v1/inference"
    asr_model: str = "qwen-audio-3.0-asr-flash-streaming"
    focus_prompt_target_tokens: int = 8_000
    focus_dialogue_target_tokens: int = 6_000
    focus_history_target_tokens: int = 1_600
    focus_characters_per_token: float = 1.7
    focus_debounce_ms: int = 300
    focus_max_coalesce_ms: int = 1_200
    focus_timeout_seconds: float = 5.0
    audit_log_dir: Path = REPO_ROOT / ".runtime" / "logs"
    audit_include_text: bool = False
    audit_ring_size: int = 1_000
    audit_queue_size: int = 4_096

    @classmethod
    def from_env(cls) -> Settings:
        load_local_env()
        audit_log_dir = Path(
            os.environ.get(
                "ANTIBAGU_LOG_DIR", str(REPO_ROOT / ".runtime" / "logs")
            )
        ).expanduser()
        if not audit_log_dir.is_absolute():
            audit_log_dir = REPO_ROOT / audit_log_dir
        return cls(
            host=os.environ.get("ANTIBAGU_SERVER_HOST", "127.0.0.1"),
            port=int(os.environ.get("ANTIBAGU_SERVER_PORT", "8765")),
            deepseek_api_key=os.environ.get("DEEPSEEK_API_KEY"),
            deepseek_base_url=os.environ.get(
                "ANTIBAGU_MODEL_BASE_URL", "https://api.deepseek.com"
            ),
            deepseek_model=os.environ.get(
                "ANTIBAGU_MODEL_NAME", "deepseek-v4-flash"
            ),
            dashscope_api_key=os.environ.get("DASHSCOPE_API_KEY"),
            dashscope_ws_url=os.environ.get(
                "ANTIBAGU_ASR_WS_URL",
                "wss://dashscope.aliyuncs.com/api-ws/v1/inference",
            ),
            asr_model=os.environ.get(
                "ANTIBAGU_ASR_MODEL", "qwen-audio-3.0-asr-flash-streaming"
            ),
            focus_prompt_target_tokens=int(
                os.environ.get("ANTIBAGU_FOCUS_PROMPT_TOKENS", "8000")
            ),
            focus_dialogue_target_tokens=int(
                os.environ.get("ANTIBAGU_FOCUS_DIALOGUE_TOKENS", "6000")
            ),
            focus_history_target_tokens=int(
                os.environ.get("ANTIBAGU_FOCUS_HISTORY_TOKENS", "1600")
            ),
            focus_characters_per_token=float(
                os.environ.get("ANTIBAGU_FOCUS_CHARACTERS_PER_TOKEN", "1.7")
            ),
            focus_debounce_ms=int(
                os.environ.get("ANTIBAGU_FOCUS_DEBOUNCE_MS", "300")
            ),
            focus_max_coalesce_ms=int(
                os.environ.get("ANTIBAGU_FOCUS_MAX_COALESCE_MS", "1200")
            ),
            focus_timeout_seconds=float(
                os.environ.get("ANTIBAGU_FOCUS_TIMEOUT_SECONDS", "5")
            ),
            audit_log_dir=audit_log_dir,
            audit_include_text=os.environ.get(
                "ANTIBAGU_LOG_INCLUDE_TEXT", "false"
            ).lower()
            in {"1", "true", "yes", "on"},
            audit_ring_size=int(os.environ.get("ANTIBAGU_LOG_RING_SIZE", "1000")),
            audit_queue_size=int(os.environ.get("ANTIBAGU_LOG_QUEUE_SIZE", "4096")),
        )
