from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from pydantic import BaseModel, Field


class FamilyRelationCreateRequest(BaseModel):
    elder_user_id: str
    family_user_id: str
    relation_type: str
    is_primary: bool = False


class FamilyRelationRecord(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    elder_user_id: str
    family_user_id: str
    relation_type: str
    is_primary: bool = False
    status: str = "active"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
