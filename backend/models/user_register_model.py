from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from backend.models.user_model import UserRole


class ElderRegisterRequest(BaseModel):
    name: str
    phone: str
    password: str = Field(min_length=6)
    age: int = Field(ge=50, le=120)
    apartment: str
    community_id: str = "community-haitang"


class FamilyRegisterRequest(BaseModel):
    name: str
    phone: str
    password: str = Field(min_length=6)
    relationship: str
    community_id: str = "community-haitang"
    login_username: str | None = None


class CommunityRegisterRequest(BaseModel):
    name: str
    phone: str
    password: str = Field(min_length=6)
    community_id: str = "community-haitang"
    login_username: str | None = None


class UserRegisterResponse(BaseModel):
    id: str
    name: str
    role: UserRole
    phone: str
    created_at: datetime
