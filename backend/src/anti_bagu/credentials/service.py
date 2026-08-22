from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from anti_bagu.persistence.models import (
    PlatformAudit,
    UserModelCredentials,
)


class ModelCredentialError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ModelCredentials:
    dashscope_api_key: str
    deepseek_api_key: str


class CredentialCipher:
    """AES-256-GCM cipher backed by a machine-local, permission-restricted key."""

    def __init__(self, key_path: Path) -> None:
        self._key_path = key_path
        self._cipher: AESGCM | None = None

    def encrypt(self, user_id: str, credentials: ModelCredentials) -> str:
        plaintext = json.dumps(
            {
                "dashscope_api_key": credentials.dashscope_api_key,
                "deepseek_api_key": credentials.deepseek_api_key,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode()
        nonce = os.urandom(12)
        ciphertext = self._get_cipher().encrypt(nonce, plaintext, self._aad(user_id))
        return base64.urlsafe_b64encode(nonce + ciphertext).decode()

    def decrypt(self, user_id: str, payload: str) -> ModelCredentials:
        try:
            decoded = base64.urlsafe_b64decode(payload.encode())
            plaintext = self._get_cipher().decrypt(
                decoded[:12], decoded[12:], self._aad(user_id)
            )
            value = json.loads(plaintext)
            return ModelCredentials(
                dashscope_api_key=str(value["dashscope_api_key"]),
                deepseek_api_key=str(value["deepseek_api_key"]),
            )
        except (InvalidTag, KeyError, ValueError, json.JSONDecodeError) as exc:
            raise ModelCredentialError("模型密钥无法解密，请在网页中重新保存") from exc

    def _get_cipher(self) -> AESGCM:
        if self._cipher is None:
            self._cipher = AESGCM(self._load_or_create_key())
        return self._cipher

    def _load_or_create_key(self) -> bytes:
        self._key_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            descriptor = os.open(
                self._key_path,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
            )
        except FileExistsError:
            pass
        else:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(os.urandom(32))
        key = self._key_path.read_bytes()
        if len(key) != 32:
            raise ModelCredentialError("服务器模型密钥加密文件无效")
        return key

    @staticmethod
    def _aad(user_id: str) -> bytes:
        return f"anti-bagu:model-credentials:{user_id}".encode()


class ModelCredentialService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        cipher: CredentialCipher,
    ) -> None:
        self._sessions = session_factory
        self._cipher = cipher

    async def get(self, user_id: str) -> ModelCredentials | None:
        async with self._sessions() as session:
            record = await session.get(UserModelCredentials, user_id)
            if record is None:
                return None
            return self._cipher.decrypt(user_id, record.encrypted_payload)

    async def configured(self, user_id: str) -> bool:
        async with self._sessions() as session:
            return await session.get(UserModelCredentials, user_id) is not None

    async def save(self, user_id: str, credentials: ModelCredentials) -> None:
        encrypted = self._cipher.encrypt(user_id, credentials)
        async with self._sessions() as session:
            record = await session.get(UserModelCredentials, user_id)
            if record is None:
                record = UserModelCredentials(user_id=user_id, encrypted_payload=encrypted)
                session.add(record)
            else:
                record.encrypted_payload = encrypted
            session.add(
                PlatformAudit(
                    actor_user_id=user_id,
                    action="model_credentials.updated",
                    target_type="model_credentials",
                    target_id=user_id,
                )
            )
            await session.commit()
