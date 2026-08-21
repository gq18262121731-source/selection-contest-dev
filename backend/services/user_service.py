from __future__ import annotations

from collections import OrderedDict
from hashlib import sha256
import re

from backend.models.formal_profile_model import CommunityStaffProfile, ElderDirectoryProfile, FamilyDirectoryProfile
from backend.models.user_model import UserRecord, UserRole
from backend.models.user_register_model import (
    CommunityRegisterRequest,
    ElderRegisterRequest,
    FamilyRegisterRequest,
    UserRegisterResponse,
)


class UserService:
    """Maintains formal user records independently from demo directory data."""

    def __init__(self) -> None:
        self._users: OrderedDict[str, UserRecord] = OrderedDict()
        self._elder_profiles: dict[str, ElderDirectoryProfile] = {}
        self._family_profiles: dict[str, FamilyDirectoryProfile] = {}
        self._community_profiles: dict[str, CommunityStaffProfile] = {}
        self._family_sequence = 0
        self._community_sequence = 0

    def register_elder(self, payload: ElderRegisterRequest) -> UserRegisterResponse:
        phone = payload.phone.strip()
        if self.get_user_by_phone(phone):
            raise ValueError("PHONE_ALREADY_EXISTS")
        record = UserRecord(
            name=payload.name.strip(),
            role=UserRole.ELDER,
            phone=phone,
            password_hash=self._hash_password(payload.password),
        )
        self._users[record.id] = record
        self._elder_profiles[record.id] = ElderDirectoryProfile(
            user_id=record.id,
            age=payload.age,
            apartment=payload.apartment.strip(),
            community_id=payload.community_id.strip(),
        )
        return self._to_response(record)

    def register_family(self, payload: FamilyRegisterRequest) -> UserRegisterResponse:
        phone = payload.phone.strip()
        if self.get_user_by_phone(phone):
            raise ValueError("PHONE_ALREADY_EXISTS")
        record = UserRecord(
            name=payload.name.strip(),
            role=UserRole.FAMILY,
            phone=phone,
            password_hash=self._hash_password(payload.password),
        )
        self._users[record.id] = record
        login_username = self._next_login_username(
            desired=payload.login_username,
            prefix="family",
            sequence_attr="_family_sequence",
        )
        self._family_profiles[record.id] = FamilyDirectoryProfile(
            user_id=record.id,
            relationship=payload.relationship.strip(),
            community_id=payload.community_id.strip(),
            login_username=login_username.strip().lower(),
        )
        return self._to_response(record)

    def register_community(self, payload: CommunityRegisterRequest) -> UserRegisterResponse:
        phone = payload.phone.strip()
        if self.get_user_by_phone(phone):
            raise ValueError("PHONE_ALREADY_EXISTS")
        record = UserRecord(
            name=payload.name.strip(),
            role=UserRole.COMMUNITY,
            phone=phone,
            password_hash=self._hash_password(payload.password),
        )
        self._users[record.id] = record
        login_username = self._next_login_username(
            desired=payload.login_username,
            prefix="community",
            sequence_attr="_community_sequence",
        )
        self._community_profiles[record.id] = CommunityStaffProfile(
            user_id=record.id,
            community_id=payload.community_id.strip(),
            login_username=login_username,
        )
        return self._to_response(record)

    def seed_elder(
        self,
        *,
        user_id: str,
        name: str,
        phone: str,
        password: str,
        age: int,
        apartment: str,
        community_id: str = "community-haitang",
    ) -> UserRecord:
        record = self._seed_user(
            user_id=user_id,
            name=name,
            role=UserRole.ELDER,
            phone=phone,
            password=password,
        )
        self._elder_profiles[record.id] = ElderDirectoryProfile(
            user_id=record.id,
            age=age,
            apartment=apartment.strip(),
            community_id=community_id.strip(),
        )
        return record

    def seed_family(
        self,
        *,
        user_id: str,
        name: str,
        phone: str,
        password: str,
        relationship: str,
        login_username: str,
        community_id: str = "community-haitang",
    ) -> UserRecord:
        normalized_login = self._normalize_login_username(login_username)
        self._ensure_seed_login_username_available(normalized_login, user_id)
        record = self._seed_user(
            user_id=user_id,
            name=name,
            role=UserRole.FAMILY,
            phone=phone,
            password=password,
        )
        self._family_profiles[record.id] = FamilyDirectoryProfile(
            user_id=record.id,
            relationship=relationship.strip(),
            community_id=community_id.strip(),
            login_username=normalized_login,
        )
        self._sync_sequence_from_seeded_username(
            prefix="family",
            username=normalized_login,
            sequence_attr="_family_sequence",
        )
        return record

    def seed_community(
        self,
        *,
        user_id: str,
        name: str,
        phone: str,
        password: str,
        login_username: str,
        community_id: str = "community-haitang",
    ) -> UserRecord:
        normalized_login = self._normalize_login_username(login_username)
        self._ensure_seed_login_username_available(normalized_login, user_id)
        record = self._seed_user(
            user_id=user_id,
            name=name,
            role=UserRole.COMMUNITY,
            phone=phone,
            password=password,
        )
        self._community_profiles[record.id] = CommunityStaffProfile(
            user_id=record.id,
            community_id=community_id.strip(),
            login_username=normalized_login,
        )
        self._sync_sequence_from_seeded_username(
            prefix="community",
            username=normalized_login,
            sequence_attr="_community_sequence",
        )
        return record

    def get_user(self, user_id: str) -> UserRecord | None:
        return self._users.get(user_id)

    def get_user_by_phone(self, phone: str) -> UserRecord | None:
        normalized = phone.strip()
        return next((user for user in self._users.values() if user.phone == normalized), None)

    def list_users(self, role: UserRole | None = None) -> list[UserRecord]:
        users = list(self._users.values())
        if role is None:
            return users
        return [user for user in users if user.role == role]

    def list_seeded_users(self, role: UserRole | None = None) -> list[UserRecord]:
        return [user for user in self.list_users(role=role) if user.is_seeded]

    def get_elder_profile(self, user_id: str) -> ElderDirectoryProfile | None:
        return self._elder_profiles.get(user_id)

    def get_family_profile(self, user_id: str) -> FamilyDirectoryProfile | None:
        return self._family_profiles.get(user_id)

    def get_community_profile(self, user_id: str) -> CommunityStaffProfile | None:
        return self._community_profiles.get(user_id)

    def authenticate_user(self, identity: str, password: str) -> UserRecord | None:
        normalized_identity = identity.strip().lower()
        if not normalized_identity:
            return None

        user = self.get_user_by_phone(normalized_identity)
        if user is None:
            user = self.get_user_by_login_username(normalized_identity)
        if user is None:
            return None
        if user.password_hash != self._hash_password(password):
            return None
        return user

    def has_formal_users(self) -> bool:
        return bool(self._users)

    def reset(self) -> None:
        self._users.clear()
        self._elder_profiles.clear()
        self._family_profiles.clear()
        self._community_profiles.clear()
        self._family_sequence = 0
        self._community_sequence = 0

    @staticmethod
    def _hash_password(password: str) -> str:
        return sha256(password.encode("utf-8")).hexdigest()

    def get_user_by_login_username(self, username: str) -> UserRecord | None:
        normalized = username.strip().lower()
        if not normalized:
            return None
        for user_id, profile in self._family_profiles.items():
            if profile.login_username == normalized:
                return self._users.get(user_id)
        for user_id, profile in self._community_profiles.items():
            if profile.login_username == normalized:
                return self._users.get(user_id)
        return None

    def _next_login_username(self, *, desired: str | None, prefix: str, sequence_attr: str) -> str:
        if desired:
            normalized_desired = self._normalize_login_username(desired)
            if self._login_username_taken(normalized_desired):
                raise ValueError("LOGIN_USERNAME_ALREADY_EXISTS")
            return normalized_desired

        while True:
            next_value = getattr(self, sequence_attr) + 1
            setattr(self, sequence_attr, next_value)
            generated = f"{prefix}{next_value:02d}"
            if not self._login_username_taken(generated):
                return generated

    def _login_username_taken(self, username: str) -> bool:
        normalized = self._normalize_login_username(username)
        return self.get_user_by_login_username(normalized) is not None

    def _seed_user(
        self,
        *,
        user_id: str,
        name: str,
        role: UserRole,
        phone: str,
        password: str,
    ) -> UserRecord:
        normalized_phone = phone.strip()
        self._ensure_seed_phone_available(normalized_phone, user_id)
        existing = self._users.get(user_id)
        if existing is not None:
            record = existing.model_copy(
                update={
                    "name": name.strip(),
                    "role": role,
                    "phone": normalized_phone,
                    "password_hash": self._hash_password(password),
                    "is_seeded": True,
                }
            )
        else:
            record = UserRecord(
                id=user_id,
                name=name.strip(),
                role=role,
                phone=normalized_phone,
                password_hash=self._hash_password(password),
                is_seeded=True,
            )
        self._users[record.id] = record
        return record

    def _ensure_seed_phone_available(self, phone: str, user_id: str) -> None:
        existing = self.get_user_by_phone(phone)
        if existing and existing.id != user_id:
            raise ValueError("PHONE_ALREADY_EXISTS")

    def _ensure_seed_login_username_available(self, username: str, user_id: str) -> None:
        existing = self.get_user_by_login_username(username)
        if existing and existing.id != user_id:
            raise ValueError("LOGIN_USERNAME_ALREADY_EXISTS")

    def _sync_sequence_from_seeded_username(self, *, prefix: str, username: str, sequence_attr: str) -> None:
        match = re.fullmatch(rf"{re.escape(prefix)}(\d+)", username)
        if not match:
            return
        current = getattr(self, sequence_attr)
        setattr(self, sequence_attr, max(current, int(match.group(1))))

    @staticmethod
    def _normalize_login_username(value: str) -> str:
        normalized = re.sub(r"\s+", "", value.strip().lower())
        if not normalized:
            raise ValueError("INVALID_LOGIN_USERNAME")
        return normalized

    @staticmethod
    def _to_response(record: UserRecord) -> UserRegisterResponse:
        return UserRegisterResponse(
            id=record.id,
            name=record.name,
            role=record.role,
            phone=record.phone,
            created_at=record.created_at,
        )
