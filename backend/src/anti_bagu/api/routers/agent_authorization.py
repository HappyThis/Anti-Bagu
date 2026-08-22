from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from anti_bagu.api.dependencies import Principal, current_principal, get_auth_service
from anti_bagu.api.schemas import AgentAuthorizationPollRequest
from anti_bagu.auth.service import AuthService

router = APIRouter(prefix="/api/v1/agent/authorizations", tags=["agent-auth"])


@router.post("")
async def begin_authorization(request: Request):
    authorization, device_secret = await request.app.state.agent_authorizations.create()
    return {
        "request_id": authorization.request_id,
        "device_secret": device_secret,
        "user_code": authorization.user_code,
        "verification_url": (
            f"{request.app.state.settings.public_base_url}/agent/authorize"
            f"?code={authorization.user_code}"
        ),
        "expires_at": authorization.expires_at,
        "poll_interval_seconds": 2,
    }


@router.post("/{request_id}/poll")
async def poll_authorization(
    request_id: str,
    payload: AgentAuthorizationPollRequest,
    request: Request,
):
    result = await request.app.state.agent_authorizations.poll(
        request_id, payload.device_secret
    )
    if result is None:
        raise HTTPException(status_code=404, detail="授权请求不存在")
    return result


@router.post("/code/{user_code}/approve")
async def approve_authorization(
    user_code: str,
    request: Request,
    principal: Principal = Depends(current_principal),
    auth: AuthService = Depends(get_auth_service),
):
    issued = await auth.issue_for_user(principal.user, kind="agent")
    authorization = await request.app.state.agent_authorizations.approve(
        user_code, issued
    )
    if authorization is None:
        await auth.revoke(issued.token)
        raise HTTPException(status_code=404, detail="授权请求已失效")
    return {"approved": True, "username": principal.user.username}


@router.post("/code/{user_code}/cancel")
async def cancel_authorization(
    user_code: str,
    request: Request,
    _: Principal = Depends(current_principal),
):
    authorization = await request.app.state.agent_authorizations.cancel(user_code)
    if authorization is None:
        raise HTTPException(status_code=404, detail="授权请求已失效")
    return {"cancelled": True}
