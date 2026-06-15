from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from backend.models.user_model import UserRole


class PushProvider(str, Enum):
    LOCAL = "local"
    FCM = "fcm"
    APNS = "apns"


class PushPlatform(str, Enum):
    ANDROID = "android"
    IOS = "ios"
    MACOS = "macos"
    WINDOWS = "windows"
    LINUX = "linux"
    WEB = "web"
    UNKNOWN = "unknown"


class MobilePushDeviceUpsertRequest(BaseModel):
    installation_id: str = Field(min_length=8, max_length=128)
    provider: PushProvider = PushProvider.LOCAL
    platform: PushPlatform = PushPlatform.UNKNOWN
    push_token: str = Field(min_length=8, max_length=512)
    notifications_enabled: bool = True
    remote_push_ready: bool = False
    app_version: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class MobilePushDeviceRecord(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    user_id: str
    role: UserRole
    family_id: str | None = None
    community_id: str | None = None
    installation_id: str
    provider: PushProvider
    platform: PushPlatform
    push_token: str
    notifications_enabled: bool = True
    remote_push_ready: bool = False
    app_version: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    revoked_at: datetime | None = None

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None


class MobilePushDispatchTarget(BaseModel):
    installation_id: str
    user_id: str
    provider: PushProvider
    platform: PushPlatform
    notifications_enabled: bool
    remote_push_ready: bool


class MobilePushDispatchRecord(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    alarm_id: str
    device_mac: str
    recipient_count: int = 0
    remote_ready_count: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    targets: list[MobilePushDispatchTarget] = Field(default_factory=list)
