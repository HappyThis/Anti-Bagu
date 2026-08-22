from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from anti_bagu.core.security import (
    hash_password,
    hash_token,
    new_activation_key,
    new_opaque_token,
    verify_password,
)
from anti_bagu.persistence.models import ActivationKey, AuthSession, PlatformAudit, User

USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9._-]{3,32}$")


class AuthError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class IssuedSession:
    token: str
    expires_at: datetime
    user: User


class AuthService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        web_session_days: int = 7,
        agent_token_days: int = 30,
    ) -> None:
        self._sessions = session_factory
        self._web_session_days = web_session_days
        self._agent_token_days = agent_token_days

    async def ensure_admin(self, username: str | None, password: str | None) -> None:
        if not username or not password:
            return
        async with self._sessions() as session:
            existing = await session.scalar(select(User).where(User.username == username))
            if existing is not None:
                return
            session.add(
                User(
                    username=username,
                    display_name="管理员",
                    password_hash=hash_password(password),
                    role="admin",
                )
            )
            await session.commit()

    async def create_activation_key(
        self,
        *,
        actor: User,
        valid_days: int = 30,
    ) -> tuple[ActivationKey, str]:
        display_key = new_activation_key()
        record = ActivationKey(
            key_hash=hash_token(display_key),
            key_hint=f"{display_key[:7]}•••••••••",
            created_by_id=actor.id,
            expires_at=datetime.now(UTC) + timedelta(days=valid_days),
        )
        async with self._sessions() as session:
            session.add(record)
            session.add(
                PlatformAudit(
                    actor_user_id=actor.id,
                    action="activation_key.created",
                    target_type="activation_key",
                    target_id=record.id,
                )
            )
            await session.commit()
            await session.refresh(record)
        return record, display_key

    async def register(
        self,
        *,
        activation_key: str,
        username: str,
        password: str,
    ) -> User:
        normalized = username.strip()
        if not USERNAME_PATTERN.fullmatch(normalized):
            raise AuthError("用户名只能包含 3–32 位字母、数字或 . _ -")
        if len(password) < 8:
            raise AuthError("密码至少需要 8 位字符")
        now = datetime.now(UTC)
        async with self._sessions() as session:
            existing = await session.scalar(select(User).where(User.username == normalized))
            if existing is not None:
                raise AuthError("用户名已存在")
            key = await session.scalar(
                select(ActivationKey)
                .where(ActivationKey.key_hash == hash_token(activation_key.strip()))
                .with_for_update()
            )
            if key is None or key.status != "unused":
                raise AuthError("激活密钥无效或已使用")
            if _as_utc(key.expires_at) <= now:
                key.status = "expired"
                await session.commit()
                raise AuthError("激活密钥已过期")
            user = User(
                username=normalized,
                display_name=normalized,
                password_hash=hash_password(password),
            )
            session.add(user)
            await session.flush()
            key.status = "used"
            key.used_by_id = user.id
            key.used_at = now
            session.add(
                PlatformAudit(
                    actor_user_id=user.id,
                    action="user.registered",
                    target_type="user",
                    target_id=user.id,
                )
            )
            await session.commit()
            await session.refresh(user)
            return user

    async def login(self, username: str, password: str, *, kind: str) -> IssuedSession:
        async with self._sessions() as session:
            user = await session.scalar(select(User).where(User.username == username.strip()))
            if (
                user is None
                or user.status != "active"
                or not verify_password(password, user.password_hash)
            ):
                raise AuthError("用户名或密码错误")
            return await self._issue(session, user, kind=kind)

    async def issue_for_user(self, user: User, *, kind: str) -> IssuedSession:
        async with self._sessions() as session:
            current = await session.get(User, user.id)
            if current is None or current.status != "active":
                raise AuthError("用户不可用")
            return await self._issue(session, current, kind=kind)

    async def resolve(self, token: str, *, kind: str | None = None) -> User | None:
        now = datetime.now(UTC)
        async with self._sessions() as session:
            statement = (
                select(AuthSession)
                .where(AuthSession.token_hash == hash_token(token))
                .where(AuthSession.revoked_at.is_(None))
            )
            if kind is not None:
                statement = statement.where(AuthSession.kind == kind)
            record = await session.scalar(statement)
            if record is None or _as_utc(record.expires_at) <= now:
                return None
            user = await session.get(User, record.user_id)
            if user is None or user.status != "active":
                return None
            record.last_seen_at = now
            await session.commit()
            return user

    async def revoke(self, token: str) -> None:
        async with self._sessions() as session:
            record = await session.scalar(
                select(AuthSession).where(AuthSession.token_hash == hash_token(token))
            )
            if record is not None:
                record.revoked_at = datetime.now(UTC)
                await session.commit()

    async def _issue(
        self, session: AsyncSession, user: User, *, kind: str
    ) -> IssuedSession:
        days = self._agent_token_days if kind == "agent" else self._web_session_days
        prefix = "aba" if kind == "agent" else "abw"
        token = new_opaque_token(prefix)
        expires_at = datetime.now(UTC) + timedelta(days=days)
        session.add(
            AuthSession(
                user_id=user.id,
                kind=kind,
                token_hash=hash_token(token),
                expires_at=expires_at,
            )
        )
        session.add(
            PlatformAudit(
                actor_user_id=user.id,
                action=f"auth.{kind}.issued",
                target_type="session",
            )
        )
        await session.commit()
        return IssuedSession(token=token, expires_at=expires_at, user=user)


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
