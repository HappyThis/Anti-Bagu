from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from anti_bagu.api.dependencies import Principal, current_principal, get_auth_service
from anti_bagu.api.schemas import LoginRequest, LoginResponse, RegisterRequest, UserView
from anti_bagu.auth.service import AuthError, AuthService

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/register", response_model=UserView, status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterRequest, auth: AuthService = Depends(get_auth_service)):
    try:
        return await auth.register(
            activation_key=payload.activation_key,
            username=payload.username,
            password=payload.password,
        )
    except AuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/login", response_model=LoginResponse)
async def login(payload: LoginRequest, auth: AuthService = Depends(get_auth_service)):
    try:
        issued = await auth.login(payload.username, payload.password, kind="web")
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    return LoginResponse(
        token=issued.token,
        expires_at=issued.expires_at,
        user=UserView.model_validate(issued.user),
    )


@router.post("/agent", response_model=LoginResponse)
async def agent_login(
    payload: LoginRequest, auth: AuthService = Depends(get_auth_service)
):
    try:
        issued = await auth.login(payload.username, payload.password, kind="agent")
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    return LoginResponse(
        token=issued.token,
        expires_at=issued.expires_at,
        user=UserView.model_validate(issued.user),
    )


@router.get("/me", response_model=UserView)
async def me(principal: Principal = Depends(current_principal)):
    return principal.user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    principal: Principal = Depends(current_principal),
    auth: AuthService = Depends(get_auth_service),
) -> None:
    await auth.revoke(principal.token)
