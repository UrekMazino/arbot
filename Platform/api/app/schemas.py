from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, EmailStr, Field


class MessageOut(BaseModel):
    message: str


class TokenPairOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    refresh_token: str


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class RefreshIn(BaseModel):
    refresh_token: str


class LogoutIn(BaseModel):
    refresh_token: str


class RoleOut(BaseModel):
    id: str
    name: str
    description: str | None = None

    model_config = {"from_attributes": True}


class UserOut(BaseModel):
    id: str
    email: EmailStr
    is_active: bool
    is_superuser: bool
    roles: list[RoleOut] = []
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class UserCreateIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    is_active: bool = True
    is_superuser: bool = False


class UserUpdateIn(BaseModel):
    is_active: bool | None = None
    is_superuser: bool | None = None
    password: str | None = Field(default=None, min_length=8)


class UserRoleAssignIn(BaseModel):
    role: str


class EventEnvelopeIn(BaseModel):
    event_id: str
    run_id: str
    ts: float
    event_type: str
    severity: str = "info"
    payload: dict[str, Any] = Field(default_factory=dict)


class EventBatchIn(BaseModel):
    events: list[EventEnvelopeIn] = Field(default_factory=list, max_length=200)


class EventIngestResultOut(BaseModel):
    accepted: int
    duplicate: int
    rejected: int


class RunOut(BaseModel):
    id: str
    bot_instance_id: str
    run_key: str
    status: str
    start_ts: datetime
    end_ts: datetime | None = None
    start_equity: float | None = None
    end_equity: float | None = None
    session_pnl: float | None = None
    max_drawdown: float | None = None

    model_config = {"from_attributes": True}


class RunEventOut(BaseModel):
    id: str
    event_id: str
    run_id: str
    ts: datetime
    event_type: str
    severity: str
    payload_json: dict[str, Any]

    model_config = {"from_attributes": True}


class TradeOut(BaseModel):
    id: str
    run_id: str
    pair_key: str
    entry_ts: datetime | None = None
    exit_ts: datetime | None = None
    side: str | None = None
    entry_z: float | None = None
    exit_z: float | None = None
    pnl_usdt: float | None = None
    hold_minutes: float | None = None
    strategy: str | None = None
    regime: str | None = None
    exit_reason: str | None = None
    entry_strategy: str | None = None
    entry_regime: str | None = None
    exit_tier: str | None = None
    entry_z_threshold_used: float | None = None
    size_multiplier_used: float | None = None

    model_config = {"from_attributes": True}
