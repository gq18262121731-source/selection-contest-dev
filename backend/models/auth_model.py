from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field

from backend.models.user_model import UserRole


class AuthAccountPreview(BaseModel):
    username: str
    display_name: str
    role: UserRole
    family_id: str | None = None
    community_id: str
    default_password: str = "123456"


class LoginRequest(BaseModel):
    username: str
    password: str = Field(min_length=1)


class SessionUser(BaseModel):
    id: str
    username: str
    name: str
    role: UserRole
    community_id: str
    family_id: str | None = None


class LoginResponse(BaseModel):
    token: str
    user: SessionUser
    expires_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc).replace(microsecond=0),
    )
