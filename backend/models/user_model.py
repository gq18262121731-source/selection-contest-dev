from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4

from pydantic import BaseModel, Field


class UserRole(str, Enum):
    ELDER = "elder"
    FAMILY = "family"
    COMMUNITY = "community"
    ADMIN = "admin"


class UserRecord(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    role: UserRole
    phone: str
    password_hash: str = ""
    is_seeded: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
