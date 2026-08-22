from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException, Request, status

from anti_bagu.auth.service import AuthService
from anti_bagu.persistence.models import User


@dataclass(frozen=True, slots=True)
class Principal:
    user: User
    token: str


async def get_db(request: Request):
    async with request.app.state.session_factory() as session:
        yield session


def get_auth_service(request: Request) -> AuthService:
    return request.app.state.auth_service


async def current_principal(
    authorization: str | None = Header(default=None),
    auth: AuthService = Depends(get_auth_service),
) -> Principal:
    token = _bearer_token(authorization)
    user = await auth.resolve(token, kind="web") if token else None
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未登录或登录已过期")
    return Principal(user=user, token=token)


async def current_admin(
    principal: Principal = Depends(current_principal),
) -> Principal:
    if principal.user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="需要管理员权限")
    return principal


def _bearer_token(value: str | None) -> str | None:
    if not value:
        return None
    scheme, _, token = value.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return token.strip()
