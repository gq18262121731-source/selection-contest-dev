from __future__ import annotations

from pydantic import BaseModel, Field


class ElderDirectoryProfile(BaseModel):
    user_id: str
    age: int = Field(ge=50, le=120)
    apartment: str
    community_id: str = "community-haitang"


class FamilyDirectoryProfile(BaseModel):
    user_id: str
    relationship: str
    community_id: str = "community-haitang"
    login_username: str


class CommunityStaffProfile(BaseModel):
    user_id: str
    community_id: str = "community-haitang"
    login_username: str
