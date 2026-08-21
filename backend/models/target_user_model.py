from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class TargetUserRecord(BaseModel):
    id: str
    display_name: str = Field(..., min_length=1, max_length=80)
    group: str = Field(default="default", min_length=1, max_length=40)
    note: str = Field(default="", max_length=500)
    enabled: bool = True
    created_at: datetime
    updated_at: datetime
    photo_count: int = 0
    face_embedding_count: int = 0
    body_profile_count: int = 0


class TargetUserCreateResponse(BaseModel):
    user: TargetUserRecord
    warnings: list[str] = Field(default_factory=list)


class TargetUserDeleteResponse(BaseModel):
    ok: bool = True
    id: str


class TargetUserMatchResult(BaseModel):
    matched: bool = False
    user_id: str | None = None
    display_name: str | None = None
    face_score: float = 0.0
    body_score: float = 0.0
    body_appearance_score: float = 0.0
    fused_score: float = 0.0
    decision: Literal["target", "non_target", "unknown"] = "unknown"
