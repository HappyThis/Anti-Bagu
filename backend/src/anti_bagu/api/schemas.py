from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class RegisterRequest(BaseModel):
    activation_key: str = Field(min_length=8, max_length=64)
    username: str = Field(min_length=3, max_length=32)
    password: str = Field(min_length=8, max_length=256)


class LoginRequest(BaseModel):
    username: str = Field(min_length=3, max_length=32)
    password: str = Field(min_length=8, max_length=256)


class UserView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    username: str
    display_name: str
    role: str
    status: str
    created_at: datetime


class LoginResponse(BaseModel):
    token: str
    token_type: Literal["bearer"] = "bearer"
    expires_at: datetime
    user: UserView


class CreateTaskRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    mode: Literal["interview", "practice"] = "interview"
    mobile_required: bool = True


class UpdateTaskRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)


class TaskView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    mode: str
    mobile_required: bool
    status: str
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    ended_at: datetime | None


class PreflightCheck(BaseModel):
    key: str
    label: str
    ok: bool
    detail: str
    latency_ms: float | None = None


class PreflightResponse(BaseModel):
    task: TaskView
    checks: list[PreflightCheck]
    ready: bool


class ActivationKeyCreateRequest(BaseModel):
    valid_days: int = Field(default=30, ge=1, le=365)


class ActivationKeyView(BaseModel):
    id: str
    key_hint: str
    status: str
    created_at: datetime
    expires_at: datetime
    bound_username: str | None = None
    display_key: str | None = None


class DeviceView(BaseModel):
    id: str
    name: str
    platform: str
    agent_version: str
    status: str
    last_seen_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)


class TaskEventView(BaseModel):
    id: int
    event_id: str
    event_type: str
    conversation_revision: int
    payload: dict[str, Any]
    created_at: datetime
