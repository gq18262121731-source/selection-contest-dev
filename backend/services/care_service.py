from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from backend.config import Settings
from backend.models.auth_model import AuthAccountPreview, LoginResponse, SessionUser
from backend.models.care_model import CareDirectory, CommunityProfile, ElderProfile, FamilyProfile
from backend.models.device_model import DeviceBindStatus, DeviceIngestMode, DeviceRecord
from backend.models.user_model import UserRole
from backend.services.device_service import DeviceService
from backend.services.relation_service import RelationService
from backend.services.user_service import UserService


RELATIONSHIP_POOL = ["女儿", "儿子", "配偶", "外孙女", "外孙", "亲属"]


def _pick_from_pool(pool: list[str], index: int, fallback_prefix: str) -> str:
    if not pool:
        return f"{fallback_prefix}{index + 1}"
    return pool[index % len(pool)]


def _build_phone(index: int) -> str:
    return f"1380000{str(1200 + index)[-4:]}"


@dataclass(slots=True)
class AccountRecord:
    username: str
    password: str
    user: SessionUser


@dataclass(frozen=True, slots=True)
class DemoFamilySeed:
    id: str
    name: str
    login_username: str


@dataclass(frozen=True, slots=True)
class DemoElderSeed:
    id: str
    login_username: str
    name: str
    apartment: str
    family_id: str
    receives_mock_device: bool


DEMO_FAMILY_SEEDS = [
    DemoFamilySeed(id="family01", name="家属 01", login_username="family01"),
    DemoFamilySeed(id="family02", name="家属 02", login_username="family02"),
    DemoFamilySeed(id="family03", name="家属 03", login_username="family03"),
    DemoFamilySeed(id="family04", name="家属 04", login_username="family04"),
    DemoFamilySeed(id="family05", name="家属 05", login_username="family05"),
    DemoFamilySeed(id="family06", name="家属 06", login_username="family06"),
]

DEMO_ELDER_SEEDS = [
    DemoElderSeed(id="elder01_01", login_username="elder01_01", name="张三", apartment="1-101", family_id="family01", receives_mock_device=False),
    DemoElderSeed(id="elder01_02", login_username="elder01_02", name="李四", apartment="1-102", family_id="family01", receives_mock_device=True),
    DemoElderSeed(id="elder02_01", login_username="elder02_01", name="王五", apartment="1-103", family_id="family02", receives_mock_device=True),
    DemoElderSeed(id="elder02_02", login_username="elder02_02", name="赵六", apartment="2-101", family_id="family02", receives_mock_device=True),
    DemoElderSeed(id="elder03_01", login_username="elder03_01", name="钱七", apartment="2-102", family_id="family03", receives_mock_device=True),
    DemoElderSeed(id="elder03_02", login_username="elder03_02", name="孙八", apartment="2-103", family_id="family03", receives_mock_device=True),
    DemoElderSeed(id="elder04_01", login_username="elder04_01", name="周九", apartment="3-101", family_id="family04", receives_mock_device=True),
    DemoElderSeed(id="elder04_02", login_username="elder04_02", name="吴十", apartment="3-102", family_id="family04", receives_mock_device=True),
    DemoElderSeed(id="elder05_01", login_username="elder05_01", name="郑十一", apartment="3-103", family_id="family05", receives_mock_device=True),
    DemoElderSeed(id="elder05_02", login_username="elder05_02", name="卫十二", apartment="4-101", family_id="family05", receives_mock_device=True),
    DemoElderSeed(id="elder06_01", login_username="elder06_01", name="韩十三", apartment="4-102", family_id="family06", receives_mock_device=True),
]


class CareService:
    """Provides directory aggregation and keeps demo auth isolated from formal registration."""

    def __init__(
        self,
        device_service: DeviceService,
        user_service: UserService,
        relation_service: RelationService,
        settings: Settings,
    ) -> None:
        self._device_service = device_service
        self._user_service = user_service
        self._relation_service = relation_service
        self._settings = settings
        self._session_store: dict[str, SessionUser] = {}
        self._session_expiry: dict[str, datetime] = {}
        self._session_ttl = timedelta(hours=12)

    def get_directory(self) -> CareDirectory:
        formal_directory = self._build_formal_directory()
        if formal_directory is not None:
            return formal_directory
        return self.get_demo_directory()

    def get_demo_directory(self) -> CareDirectory:
        return self._build_demo_directory(self._device_service.list_devices())

    def get_family_directory(self, family_id: str) -> CareDirectory:
        directory = self.get_directory()
        family = next((item for item in directory.families if item.id == family_id), None)
        if family is None:
            directory = self.get_demo_directory()
            family = next((item for item in directory.families if item.id == family_id), None)
        if not family:
            return CareDirectory(community=directory.community, elders=[], families=[])
        elder_ids = list(family.elder_ids)
        if not elder_ids:
            elder_ids = self.resolve_family_elder_ids(family_id)
            if elder_ids:
                family = family.model_copy(update={"elder_ids": elder_ids})
        elder_set = set(elder_ids)
        elders = [elder for elder in directory.elders if elder.id in elder_set]
        return CareDirectory(community=directory.community, elders=elders, families=[family])

    def resolve_family_elder_ids(self, family_user_id: str) -> list[str]:
        explicit_elder_ids = [
            relation.elder_user_id
            for relation in self._relation_service.list_relations_by_family(family_user_id)
            if relation.status == "active"
        ]
        if explicit_elder_ids:
            return explicit_elder_ids

        family_profile = self._user_service.get_family_profile(family_user_id)
        if family_profile is None:
            return []

        community_family_ids = [
            user.id
            for user in self._user_service.list_users(role=UserRole.FAMILY)
            if (profile := self._user_service.get_family_profile(user.id))
            and profile.community_id == family_profile.community_id
        ]
        if community_family_ids != [family_user_id]:
            return []

        community_elder_ids = [
            user.id
            for user in self._user_service.list_users(role=UserRole.ELDER)
            if (profile := self._user_service.get_elder_profile(user.id))
            and profile.community_id == family_profile.community_id
        ]
        if len(community_elder_ids) == 1:
            return community_elder_ids

        bound_elder_ids = sorted(
            {
                device.user_id
                for device in self._device_service.list_devices()
                if device.user_id
                and device.user_id in community_elder_ids
                and device.bind_status == DeviceBindStatus.BOUND
            }
        )
        if len(bound_elder_ids) == 1:
            return bound_elder_ids

        return []

    def list_auth_accounts(self) -> list[AuthAccountPreview]:
        records = self._build_demo_accounts()
        return [
            AuthAccountPreview(
                username=record.username,
                display_name=record.user.name,
                role=record.user.role,
                family_id=record.user.family_id,
                community_id=record.user.community_id,
                default_password=record.password,
            )
            for record in records
        ]

    def login(self, username: str, password: str) -> LoginResponse | None:
        formal = self.login_formal(username, password)
        if formal is not None:
            return formal
        return self.login_demo(username, password)

    def login_demo(self, username: str, password: str) -> LoginResponse | None:
        normalized_username = username.strip().lower()
        record = next((item for item in self._build_demo_accounts() if item.username == normalized_username), None)
        if not record or record.password != password:
            return None
        return self._open_session(record.user)

    def login_formal(self, username: str, password: str) -> LoginResponse | None:
        user = self._user_service.authenticate_user(username, password)
        if user is None:
            return None
        session_user = self._build_formal_session_user(user)
        if session_user is None:
            return None
        return self._open_session(session_user)

    def _open_session(self, user: SessionUser) -> LoginResponse:
        token = str(uuid4())
        self._session_store[token] = user
        self._session_expiry[token] = datetime.now(timezone.utc) + self._session_ttl
        return LoginResponse(token=token, user=user, expires_at=self._session_expiry[token])

    def resolve_session(self, token: str) -> SessionUser | None:
        normalized = token.strip()
        if not normalized:
            return None
        expires_at = self._session_expiry.get(normalized)
        if expires_at is None:
            return None
        if expires_at < datetime.now(timezone.utc):
            self._session_expiry.pop(normalized, None)
            self._session_store.pop(normalized, None)
            return None
        return self._session_store.get(normalized)

    def reset_sessions(self) -> None:
        self._session_store.clear()
        self._session_expiry.clear()

    def _build_formal_directory(self) -> CareDirectory | None:
        if not self._user_service.has_formal_users():
            return None
        community = self._community_profile()
        devices_by_user: dict[str, list[DeviceRecord]] = {}
        for device in self._device_service.list_devices():
            if device.user_id:
                devices_by_user.setdefault(device.user_id, []).append(device)

        elders: list[ElderProfile] = []
        for user in self._user_service.list_users(role=UserRole.ELDER):
            profile = self._user_service.get_elder_profile(user.id)
            if profile is None:
                continue
            relations = self._relation_service.list_relations_by_elder(user.id)
            elder_devices = sorted(devices_by_user.get(user.id, []), key=lambda item: item.created_at)
            elder_device_macs = [device.mac_address for device in elder_devices]
            elders.append(
                ElderProfile(
                    id=user.id,
                    name=user.name,
                    age=profile.age,
                    apartment=profile.apartment,
                    community_id=profile.community_id,
                    device_mac=elder_device_macs[0] if elder_device_macs else "",
                    device_macs=elder_device_macs,
                    family_ids=[relation.family_user_id for relation in relations if relation.status == "active"],
                )
            )

        families: list[FamilyProfile] = []
        for user in self._user_service.list_users(role=UserRole.FAMILY):
            profile = self._user_service.get_family_profile(user.id)
            if profile is None:
                continue
            relations = self._relation_service.list_relations_by_family(user.id)
            families.append(
                FamilyProfile(
                    id=user.id,
                    name=user.name,
                    relationship=profile.relationship,
                    phone=user.phone,
                    community_id=profile.community_id,
                    elder_ids=[relation.elder_user_id for relation in relations if relation.status == "active"],
                    login_username=profile.login_username,
                )
            )

        return CareDirectory(community=community, elders=elders, families=families)

    def _build_demo_accounts(self) -> list[AccountRecord]:
        directory = self.get_demo_directory()
        community_user = SessionUser(
            id=directory.community.id,
            username="community_admin",
            name="社区管理员",
            role=UserRole.COMMUNITY,
            community_id=directory.community.id,
            family_id=None,
        )
        records = [AccountRecord(username="community_admin", password=self._settings.seed_default_password, user=community_user)]
        demo_elder_username_by_id = {seed.id: seed.login_username.lower() for seed in DEMO_ELDER_SEEDS}
        for family in directory.families:
            records.append(
                AccountRecord(
                    username=family.login_username.lower(),
                    password=self._settings.seed_default_password,
                    user=SessionUser(
                        id=family.id,
                        username=family.login_username.lower(),
                        name=family.name,
                        role=UserRole.FAMILY,
                        community_id=directory.community.id,
                        family_id=family.id,
                    ),
                )
            )
            for elder_id in family.elder_ids:
                elder = next((item for item in directory.elders if item.id == elder_id), None)
                if elder is None:
                    continue
                elder_username = demo_elder_username_by_id.get(elder.id, elder.id.lower())
                records.append(
                    AccountRecord(
                        username=elder_username,
                        password=self._settings.seed_default_password,
                        user=SessionUser(
                            id=elder.id,
                            username=elder_username,
                            name=elder.name,
                            role=UserRole.ELDER,
                            community_id=directory.community.id,
                            family_id=family.id,
                        ),
                    )
                )
        return records

    def _build_formal_session_user(self, user) -> SessionUser | None:
        if user.role == UserRole.ELDER:
            profile = self._user_service.get_elder_profile(user.id)
            if profile is None:
                return None
            return SessionUser(
                id=user.id,
                username=user.phone,
                name=user.name,
                role=user.role,
                community_id=profile.community_id,
                family_id=None,
            )

        if user.role == UserRole.FAMILY:
            profile = self._user_service.get_family_profile(user.id)
            if profile is None:
                return None
            return SessionUser(
                id=user.id,
                username=profile.login_username,
                name=user.name,
                role=user.role,
                community_id=profile.community_id,
                family_id=user.id,
            )

        if user.role == UserRole.COMMUNITY:
            profile = self._user_service.get_community_profile(user.id)
            if profile is None:
                return None
            return SessionUser(
                id=user.id,
                username=profile.login_username,
                name=user.name,
                role=user.role,
                community_id=profile.community_id,
                family_id=None,
            )

        return None

    def _build_demo_directory(self, devices: list[DeviceRecord]) -> CareDirectory:
        mock_devices = sorted(
            [d for d in devices if str(getattr(d, "ingest_mode", "")) in ("mock", "DeviceIngestMode.MOCK", "")],
            key=lambda item: item.mac_address,
        )
        bound_real_devices_by_user: dict[str, list[DeviceRecord]] = {}
        for device in sorted(devices, key=lambda item: (item.created_at, item.mac_address)):
            if not device.user_id or device.bind_status != DeviceBindStatus.BOUND:
                continue
            if device.ingest_mode == DeviceIngestMode.MOCK:
                continue
            bound_real_devices_by_user.setdefault(device.user_id, []).append(device)
        community = self._community_profile()
        family_map = {
            family.id: FamilyProfile(
                id=family.id,
                name=family.name,
                relationship=_pick_from_pool(RELATIONSHIP_POOL, index, "relative"),
                phone=_build_phone(index),
                community_id=community.id,
                elder_ids=[],
                login_username=family.login_username,
            )
            for index, family in enumerate(DEMO_FAMILY_SEEDS)
        }
        mock_device_macs = [device.mac_address for device in mock_devices]
        mock_device_index = 0
        elders: list[ElderProfile] = []
        for index, elder_seed in enumerate(DEMO_ELDER_SEEDS):
            assigned_mac = ""
            device_macs: list[str] = []
            bound_real_devices = bound_real_devices_by_user.get(elder_seed.id, [])
            if bound_real_devices:
                device_macs = [device.mac_address for device in bound_real_devices]
                assigned_mac = device_macs[0]
            elif elder_seed.receives_mock_device and mock_device_index < len(mock_device_macs):
                assigned_mac = mock_device_macs[mock_device_index]
                device_macs = [assigned_mac]
                mock_device_index += 1
            elder = ElderProfile(
                id=elder_seed.id,
                name=elder_seed.name,
                age=67 + (index % 17),
                apartment=elder_seed.apartment,
                community_id=community.id,
                device_mac=assigned_mac,
                device_macs=device_macs,
                family_ids=[elder_seed.family_id],
            )
            elders.append(elder)
            family_map[elder_seed.family_id].elder_ids.append(elder.id)

        return CareDirectory(
            community=community,
            elders=elders,
            families=[family_map[family.id] for family in DEMO_FAMILY_SEEDS],
        )

    @staticmethod
    def _community_profile() -> CommunityProfile:
        return CommunityProfile(
            id="community-haitang",
            name="海棠社区",
            address="海棠路 68 号",
            manager="社区值班中心",
            hotline="400-810-6868",
        )
