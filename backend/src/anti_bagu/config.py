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
    deepseek_model: str = "deepseek-v4-flash-vision-exp"
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
    screenshot_focus_timeout_seconds: float = 60.0
    audit_log_dir: Path = REPO_ROOT / ".runtime" / "logs"
    audit_include_text: bool = False
    audit_ring_size: int = 1_000
    audit_queue_size: int = 4_096
    database_url: str = f"sqlite+aiosqlite:///{REPO_ROOT / '.runtime' / 'anti_bagu.db'}"
    storage_dir: Path = REPO_ROOT / ".runtime" / "storage"
    credential_key_path: Path = REPO_ROOT / ".runtime" / "credential-encryption.key"
    public_base_url: str = "http://127.0.0.1:5174"
    cors_origins: tuple[str, ...] = (
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "http://127.0.0.1:5174",
        "http://localhost:5174",
    )
    web_session_days: int = 7
    agent_token_days: int = 30
    admin_username: str | None = None
    admin_password: str | None = None
    auto_create_schema: bool = True

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
        storage_dir = Path(
            os.environ.get("ANTIBAGU_STORAGE_DIR", str(REPO_ROOT / ".runtime" / "storage"))
        ).expanduser()
        if not storage_dir.is_absolute():
            storage_dir = REPO_ROOT / storage_dir
        credential_key_path = Path(
            os.environ.get(
                "ANTIBAGU_CREDENTIAL_KEY_PATH",
                str(storage_dir.parent / "credential-encryption.key"),
            )
        ).expanduser()
        if not credential_key_path.is_absolute():
            credential_key_path = REPO_ROOT / credential_key_path
        default_database = f"sqlite+aiosqlite:///{REPO_ROOT / '.runtime' / 'anti_bagu.db'}"
        cors_origins = tuple(
            origin.strip()
            for origin in os.environ.get(
                "ANTIBAGU_CORS_ORIGINS",
                "http://127.0.0.1:5173,http://localhost:5173,http://127.0.0.1:5174,http://localhost:5174",
            ).split(",")
            if origin.strip()
        )
        return cls(
            host=os.environ.get("ANTIBAGU_SERVER_HOST", "127.0.0.1"),
            port=int(os.environ.get("ANTIBAGU_SERVER_PORT", "8765")),
            deepseek_api_key=os.environ.get("DEEPSEEK_API_KEY"),
            deepseek_base_url=os.environ.get(
                "ANTIBAGU_MODEL_BASE_URL", "https://api.deepseek.com"
            ),
            deepseek_model=os.environ.get(
                "ANTIBAGU_MODEL_NAME", "deepseek-v4-flash-vision-exp"
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
            screenshot_focus_timeout_seconds=float(
                os.environ.get("ANTIBAGU_SCREENSHOT_FOCUS_TIMEOUT_SECONDS", "60")
            ),
            audit_log_dir=audit_log_dir,
            audit_include_text=os.environ.get(
                "ANTIBAGU_LOG_INCLUDE_TEXT", "false"
            ).lower()
            in {"1", "true", "yes", "on"},
            audit_ring_size=int(os.environ.get("ANTIBAGU_LOG_RING_SIZE", "1000")),
            audit_queue_size=int(os.environ.get("ANTIBAGU_LOG_QUEUE_SIZE", "4096")),
            database_url=os.environ.get("ANTIBAGU_DATABASE_URL", default_database),
            storage_dir=storage_dir,
            credential_key_path=credential_key_path,
            public_base_url=os.environ.get(
                "ANTIBAGU_PUBLIC_BASE_URL", "http://127.0.0.1:5174"
            ).rstrip("/"),
            cors_origins=cors_origins,
            web_session_days=int(os.environ.get("ANTIBAGU_WEB_SESSION_DAYS", "7")),
            agent_token_days=int(os.environ.get("ANTIBAGU_AGENT_TOKEN_DAYS", "30")),
            admin_username=os.environ.get("ANTIBAGU_ADMIN_USERNAME"),
            admin_password=os.environ.get("ANTIBAGU_ADMIN_PASSWORD"),
            auto_create_schema=os.environ.get(
                "ANTIBAGU_AUTO_CREATE_SCHEMA", "true"
            ).lower()
            in {"1", "true", "yes", "on"},
        )
