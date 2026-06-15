from __future__ import annotations

import asyncio
from types import SimpleNamespace

from backend.api import care_api, device_api
from backend.models.auth_model import SessionUser
from backend.config import Settings
from backend.models.device_bind_model import DeviceBindRequest, DeviceRebindRequest
from backend.models.device_model import (
    DeviceBindStatus,
    DeviceIngestMode,
    DeviceRecord,
    DeviceRegisterRequest,
    DeviceStatus,
    SerialTargetSwitchRequest,
    ingest_source_matches_mode,
    normalize_and_validate_mac,
)
from backend.models.health_model import IngestionSource
from backend.models.user_model import UserRole
from backend.services.care_service import CareService
from backend.services.device_service import DeviceService
from backend.services.relation_service import RelationService
from backend.services.user_service import UserService


def test_ingest_source_matches_mode() -> None:
    assert ingest_source_matches_mode(DeviceIngestMode.SERIAL, IngestionSource.SERIAL) is True
    assert ingest_source_matches_mode(DeviceIngestMode.MOCK, IngestionSource.MOCK) is True
    assert ingest_source_matches_mode(DeviceIngestMode.SERIAL, IngestionSource.MOCK) is False
    assert ingest_source_matches_mode("serial", "mock") is False


def test_compact_mac_is_normalized_for_registration() -> None:
    assert normalize_and_validate_mac("535708020001") == "53:57:08:02:00:01"
    assert normalize_and_validate_mac("53-57-08-02-00-01") == "53:57:08:02:00:01"
    assert normalize_and_validate_mac("5410260100DF") == "54:10:26:01:00:DF"
    assert normalize_and_validate_mac("54:10:26:01:00:DF") == "54:10:26:01:00:DF"


def test_registering_real_serial_device_detaches_mock_binding(tmp_path) -> None:
    user_service = UserService()
    elder = user_service.seed_elder(
        user_id="user-elder-demo",
        name="李秀英",
        phone="13900009999",
        password="123456",
        age=79,
        apartment="1-102",
    )
    service = DeviceService(
        user_service,
        database_url=f"sqlite+aiosqlite:///{(tmp_path / 'device-demo.db').as_posix()}",
    )

    mock_device = service.register_device(
        DeviceRegisterRequest(
            mac_address="53:57:08:03:00:01",
            device_name="T10-WATCH",
            user_id=elder.id,
            ingest_mode=DeviceIngestMode.MOCK,
        )
    )
    serial_device = service.register_device(
        DeviceRegisterRequest(
            mac_address="53:57:08:03:00:02",
            device_name="T10-WATCH",
            user_id=elder.id,
            ingest_mode=DeviceIngestMode.SERIAL,
        )
    )

    refreshed_mock = service.get_device(mock_device.mac_address)
    refreshed_serial = service.get_device(serial_device.mac_address)

    assert refreshed_mock is not None
    assert refreshed_serial is not None
    assert refreshed_mock.user_id is None
    assert refreshed_mock.bind_status == DeviceBindStatus.UNBOUND
    assert refreshed_serial.user_id == elder.id
    assert refreshed_serial.bind_status == DeviceBindStatus.BOUND
    assert service.get_active_serial_target_mac() == refreshed_serial.mac_address


def test_latest_serial_registration_becomes_active_target_and_falls_back_on_delete(tmp_path) -> None:
    user_service = UserService()
    elder = user_service.seed_elder(
        user_id="user-elder-target",
        name="测试老人",
        phone="13900008888",
        password="123456",
        age=76,
        apartment="2-202",
    )
    service = DeviceService(
        user_service,
        database_url=f"sqlite+aiosqlite:///{(tmp_path / 'device-target.db').as_posix()}",
    )

    first = service.register_device(
        DeviceRegisterRequest(
            mac_address="53:57:08:04:00:01",
            device_name="T10-WATCH",
            user_id=elder.id,
            ingest_mode=DeviceIngestMode.SERIAL,
        )
    )
    second = service.register_device(
        DeviceRegisterRequest(
            mac_address="53:57:08:04:00:02",
            device_name="T10-WATCH",
            ingest_mode=DeviceIngestMode.SERIAL,
        )
    )

    assert service.get_active_serial_target_mac() == second.mac_address

    service.delete_device(second.mac_address)

    assert service.get_active_serial_target_mac() == first.mac_address


def test_register_serial_device_without_binding_is_allowed_even_when_elder_has_same_model(tmp_path) -> None:
    user_service = UserService()
    elder = user_service.seed_elder(
        user_id="user-elder-unbound-demo",
        name="空挂演示老人",
        phone="13900007777",
        password="123456",
        age=75,
        apartment="3-301",
    )
    service = DeviceService(
        user_service,
        database_url=f"sqlite+aiosqlite:///{(tmp_path / 'device-unbound.db').as_posix()}",
    )

    bound = service.register_device(
        DeviceRegisterRequest(
            mac_address="54:10:26:01:00:01",
            device_name="T10-WATCH",
            user_id=elder.id,
            ingest_mode=DeviceIngestMode.SERIAL,
        )
    )

    unbound = service.register_device(
        DeviceRegisterRequest(
            mac_address="54:10:26:01:00:02",
            device_name="T10-WATCH",
            ingest_mode=DeviceIngestMode.SERIAL,
        )
    )

    assert bound.user_id == elder.id
    assert unbound.user_id is None
    assert unbound.bind_status == DeviceBindStatus.UNBOUND
    assert service.get_active_serial_target_mac() == unbound.mac_address


def test_can_switch_active_serial_target_explicitly(tmp_path) -> None:
    service = DeviceService(
        UserService(),
        database_url=f"sqlite+aiosqlite:///{(tmp_path / 'device-switch.db').as_posix()}",
    )

    first = service.register_device(
        DeviceRegisterRequest(
            mac_address="54:10:26:01:00:11",
            device_name="T10-WATCH",
            ingest_mode=DeviceIngestMode.SERIAL,
        )
    )
    second = service.register_device(
        DeviceRegisterRequest(
            mac_address="54:10:26:01:00:12",
            device_name="T10-WATCH",
            ingest_mode=DeviceIngestMode.SERIAL,
        )
    )

    active, previous = service.set_active_serial_target(first.mac_address)

    assert previous == second.mac_address
    assert active.mac_address == first.mac_address
    assert service.get_active_serial_target_mac() == first.mac_address


def test_switching_mock_device_as_serial_target_is_rejected(tmp_path) -> None:
    service = DeviceService(
        UserService(),
        database_url=f"sqlite+aiosqlite:///{(tmp_path / 'device-switch-mock.db').as_posix()}",
    )
    device = service.register_device(
        DeviceRegisterRequest(
            mac_address="53:57:08:03:00:10",
            device_name="T10-WATCH",
            ingest_mode=DeviceIngestMode.MOCK,
        )
    )

    try:
        service.set_active_serial_target(device.mac_address)
    except ValueError as exc:
        assert str(exc) == "DEVICE_NOT_SERIAL"
    else:
        raise AssertionError("expected switching mock device to fail")


def test_demo_directory_strictly_matches_setup_account_layout(tmp_path) -> None:
    user_service = UserService()
    device_service = DeviceService(
        user_service,
        database_url=f"sqlite+aiosqlite:///{(tmp_path / 'care-demo.db').as_posix()}",
    )
    relation_service = RelationService(user_service)
    care_service = CareService(device_service, user_service, relation_service, Settings())

    first_mock_device = DeviceRecord(
        mac_address="53:57:08:00:00:06",
        device_name="T10-WATCH",
        ingest_mode=DeviceIngestMode.MOCK,
        status=DeviceStatus.ONLINE,
    )
    mock_device = DeviceRecord(
        mac_address="53:57:08:00:00:07",
        device_name="T10-WATCH",
        ingest_mode=DeviceIngestMode.MOCK,
        status=DeviceStatus.ONLINE,
    )
    serial_device = DeviceRecord(
        mac_address="76:81:EE:EC:66:88",
        device_name="T10-WATCH-REAL",
        ingest_mode=DeviceIngestMode.SERIAL,
        status=DeviceStatus.ONLINE,
    )
    device_service.seed_devices([serial_device, mock_device, first_mock_device])

    directory = care_service.get_demo_directory()
    accounts = care_service.list_auth_accounts()
    family01 = next((family for family in directory.families if family.login_username == "family01"), None)
    zhang_san = next((elder for elder in directory.elders if elder.name == "张三"), None)
    li_si = next((elder for elder in directory.elders if elder.name == "李四"), None)

    assert [account.username for account in accounts[:4]] == [
        "community_admin",
        "family01",
        "elder01_01",
        "elder01_02",
    ]
    assert family01 is not None
    assert family01.id == "family01"
    assert family01.elder_ids == ["elder01_01", "elder01_02"]
    assert wang_xiuying is not None
    assert wang_xiuying.id == "elder01_01"
    assert li_jianguo is not None
    assert li_jianguo.id == "elder01_02"
    assert wang_xiuying.device_macs == []
    assert li_jianguo.device_mac == first_mock_device.mac_address
    assert serial_device.mac_address not in li_jianguo.device_macs


def test_demo_bound_serial_device_uses_demo_elder_mapping_in_metrics(monkeypatch, tmp_path) -> None:
    user_service = UserService()
    device_service = DeviceService(
        user_service,
        database_url=f"sqlite+aiosqlite:///{(tmp_path / 'care-demo-metrics.db').as_posix()}",
    )
    relation_service = RelationService(user_service)
    care_service = CareService(device_service, user_service, relation_service, Settings())
    bound_serial = DeviceRecord(
        mac_address="76:81:EE:EC:66:88",
        device_name="T10-WATCH-REAL",
        ingest_mode=DeviceIngestMode.SERIAL,
        status=DeviceStatus.ONLINE,
        bind_status=DeviceBindStatus.BOUND,
        user_id="elder01_01",
    )

    monkeypatch.setattr(care_api, "get_user_service", lambda: user_service)
    monkeypatch.setattr(care_api, "get_care_service", lambda: care_service)
    monkeypatch.setattr(care_api, "get_display_latest_sample", lambda *_args, **_kwargs: None)

    metrics = care_api._device_metrics([bound_serial])

    assert len(metrics) == 1
    assert metrics[0].elder_id == "elder01_01"
    assert metrics[0].elder_name == "张三"


def test_demo_elder_account_ids_are_valid_binding_targets() -> None:
    assert DeviceService._is_demo_elder_user_id("elder01_01") is True
    assert DeviceService._is_demo_elder_user_id("elder06_01") is True
    assert DeviceService._is_demo_elder_user_id("family01") is False


def test_formal_family_directory_infers_single_elder_without_explicit_relation(tmp_path) -> None:
    user_service = UserService()
    elder = user_service.seed_elder(
        user_id="elder-solo",
        name="鍗曚汉鑰佷汉",
        phone="13900006661",
        password="123456",
        age=72,
        apartment="5-501",
    )
    family = user_service.seed_family(
        user_id="family-solo",
        name="鍗曚汉瀹跺睘",
        phone="13900006662",
        password="123456",
        relationship="daughter",
        login_username="familysolo",
    )
    device_service = DeviceService(
        user_service,
        database_url=f"sqlite+aiosqlite:///{(tmp_path / 'care-formal-infer.db').as_posix()}",
    )
    relation_service = RelationService(user_service)
    care_service = CareService(device_service, user_service, relation_service, Settings())

    device_service.register_device(
        DeviceRegisterRequest(
            mac_address="54:10:26:01:10:01",
            device_name="T10-WATCH",
            user_id=elder.id,
            ingest_mode=DeviceIngestMode.SERIAL,
        )
    )

    directory = care_service.get_family_directory(family.id)

    assert [item.id for item in directory.elders] == [elder.id]


def test_formal_family_access_profile_can_see_single_elder_bound_device_without_relation(
    monkeypatch,
    tmp_path,
) -> None:
    user_service = UserService()
    elder = user_service.seed_elder(
        user_id="elder-access",
        name="鍙鑰佷汉",
        phone="13900006671",
        password="123456",
        age=74,
        apartment="6-601",
    )
    family = user_service.seed_family(
        user_id="family-access",
        name="鍙瀹跺睘",
        phone="13900006672",
        password="123456",
        relationship="son",
        login_username="familyaccess",
    )
    device_service = DeviceService(
        user_service,
        database_url=f"sqlite+aiosqlite:///{(tmp_path / 'care-formal-access.db').as_posix()}",
    )
    relation_service = RelationService(user_service)
    care_service = CareService(device_service, user_service, relation_service, Settings())

    device = device_service.register_device(
        DeviceRegisterRequest(
            mac_address="54:10:26:01:10:02",
            device_name="T10-WATCH",
            user_id=elder.id,
            ingest_mode=DeviceIngestMode.SERIAL,
        )
    )

    monkeypatch.setattr(care_api, "get_device_service", lambda: device_service)
    monkeypatch.setattr(care_api, "get_care_service", lambda: care_service)

    elder_ids, devices = care_api._user_bound_devices(
        SessionUser(
            id=family.id,
            username="familyaccess",
            name=family.name,
            role=UserRole.FAMILY,
            community_id="community-haitang",
            family_id=family.id,
        )
    )

    assert elder_ids == [elder.id]
    assert [item.mac_address for item in devices] == [device.mac_address]


def test_formal_family_inference_stays_off_when_community_has_multiple_families(tmp_path) -> None:
    user_service = UserService()
    elder = user_service.seed_elder(
        user_id="elder-shared",
        name="澶氬搴€佷汉",
        phone="13900006681",
        password="123456",
        age=76,
        apartment="7-701",
    )
    first_family = user_service.seed_family(
        user_id="family-first",
        name="瀹跺睘涓€",
        phone="13900006682",
        password="123456",
        relationship="daughter",
        login_username="familyfirst",
    )
    user_service.seed_family(
        user_id="family-second",
        name="瀹跺睘浜?",
        phone="13900006683",
        password="123456",
        relationship="son",
        login_username="familysecond",
    )
    device_service = DeviceService(
        user_service,
        database_url=f"sqlite+aiosqlite:///{(tmp_path / 'care-formal-safe.db').as_posix()}",
    )
    relation_service = RelationService(user_service)
    care_service = CareService(device_service, user_service, relation_service, Settings())

    device_service.register_device(
        DeviceRegisterRequest(
            mac_address="54:10:26:01:10:03",
            device_name="T10-WATCH",
            user_id=elder.id,
            ingest_mode=DeviceIngestMode.SERIAL,
        )
    )

    assert care_service.resolve_family_elder_ids(first_family.id) == []


def test_serial_target_switch_api_returns_new_target(monkeypatch, tmp_path) -> None:
    service = DeviceService(
        UserService(),
        database_url=f"sqlite+aiosqlite:///{(tmp_path / 'device-switch-api.db').as_posix()}",
    )
    first = service.register_device(
        DeviceRegisterRequest(
            mac_address="54:10:26:01:00:21",
            device_name="T10-WATCH",
            ingest_mode=DeviceIngestMode.SERIAL,
        )
    )
    second = service.register_device(
        DeviceRegisterRequest(
            mac_address="54:10:26:01:00:22",
            device_name="T10-WATCH",
            ingest_mode=DeviceIngestMode.SERIAL,
        )
    )

    monkeypatch.setattr(device_api, "get_device_service", lambda: service)
    monkeypatch.setattr(
        device_api,
        "require_write_session_user",
        lambda _authorization: SessionUser(
            id="community-demo",
            username="community_demo",
            name="社区演示账号",
            role=UserRole.COMMUNITY,
            community_id="C10001",
        ),
    )

    result = asyncio.run(
        device_api.switch_serial_target(
            SerialTargetSwitchRequest(mac_address=first.mac_address),
            authorization="Bearer demo-token",
        )
    )

    assert result.active_target_mac == first.mac_address
    assert result.previous_target_mac == second.mac_address
    assert result.active_target_device_name == first.device_name
    assert service.get_active_serial_target_mac() == first.mac_address


def test_bind_device_switch_to_serial_refreshes_active_target(tmp_path) -> None:
    user_service = UserService()
    elder = user_service.seed_elder(
        user_id="user-elder-bind-switch",
        name="杩愯鍒囨崲鑰佷汉",
        phone="13900001234",
        password="123456",
        age=78,
        apartment="8-801",
    )
    service = DeviceService(
        user_service,
        database_url=f"sqlite+aiosqlite:///{(tmp_path / 'device-bind-switch.db').as_posix()}",
    )
    serial_target = service.register_device(
        DeviceRegisterRequest(
            mac_address="54:10:26:01:00:41",
            device_name="T10-WATCH",
            user_id=elder.id,
            ingest_mode=DeviceIngestMode.SERIAL,
        )
    )
    ble_device = service.register_device(
        DeviceRegisterRequest(
            mac_address="54:10:26:01:00:42",
            device_name="T10-WATCH-B",
            ingest_mode=DeviceIngestMode.BLE,
        )
    )
    assert service.get_active_serial_target_mac() == serial_target.mac_address

    service.bind_device(
        DeviceBindRequest(
            mac_address=ble_device.mac_address,
            target_user_id=elder.id,
            new_ingest_mode=DeviceIngestMode.SERIAL,
        )
    )

    assert service.get_active_serial_target_mac() == ble_device.mac_address


def test_binding_existing_serial_device_makes_it_active_target_even_if_newer_target_exists(tmp_path) -> None:
    user_service = UserService()
    elder = user_service.seed_elder(
        user_id="user-elder-bind-existing-serial",
        name="重新绑定老人",
        phone="13900002222",
        password="123456",
        age=79,
        apartment="9-901",
    )
    service = DeviceService(
        user_service,
        database_url=f"sqlite+aiosqlite:///{(tmp_path / 'device-bind-existing-serial.db').as_posix()}",
    )
    older_serial = service.register_device(
        DeviceRegisterRequest(
            mac_address="54:10:26:01:00:51",
            device_name="T10-WATCH",
            ingest_mode=DeviceIngestMode.SERIAL,
        )
    )
    newer_serial = service.register_device(
        DeviceRegisterRequest(
            mac_address="54:10:26:01:00:52",
            device_name="T10-WATCH-B",
            ingest_mode=DeviceIngestMode.SERIAL,
        )
    )

    assert service.get_active_serial_target_mac() == newer_serial.mac_address

    service.bind_device(
        DeviceBindRequest(
            mac_address=older_serial.mac_address,
            target_user_id=elder.id,
        )
    )

    assert service.get_active_serial_target_mac() == older_serial.mac_address


def test_rebinding_existing_serial_device_makes_it_active_target_even_if_newer_target_exists(tmp_path) -> None:
    user_service = UserService()
    old_elder = user_service.seed_elder(
        user_id="user-elder-old-owner",
        name="旧归属老人",
        phone="13900003333",
        password="123456",
        age=80,
        apartment="10-1001",
    )
    new_elder = user_service.seed_elder(
        user_id="user-elder-new-owner",
        name="新归属老人",
        phone="13900004444",
        password="123456",
        age=78,
        apartment="10-1002",
    )
    service = DeviceService(
        user_service,
        database_url=f"sqlite+aiosqlite:///{(tmp_path / 'device-rebind-existing-serial.db').as_posix()}",
    )
    older_serial = service.register_device(
        DeviceRegisterRequest(
            mac_address="54:10:26:01:00:61",
            device_name="T10-WATCH",
            user_id=old_elder.id,
            ingest_mode=DeviceIngestMode.SERIAL,
        )
    )
    newer_serial = service.register_device(
        DeviceRegisterRequest(
            mac_address="54:10:26:01:00:62",
            device_name="T10-WATCH-B",
            ingest_mode=DeviceIngestMode.SERIAL,
        )
    )

    assert service.get_active_serial_target_mac() == newer_serial.mac_address

    service.rebind_device(
        DeviceRebindRequest(
            mac_address=older_serial.mac_address,
            new_user_id=new_elder.id,
        )
    )

    assert service.get_active_serial_target_mac() == older_serial.mac_address


def test_unbind_self_prioritizes_active_serial_target(monkeypatch, tmp_path) -> None:
    user_service = UserService()
    elder = user_service.seed_elder(
        user_id="elder-unbind-self",
        name="解绑自测老人",
        phone="13900001111",
        password="123456",
        age=77,
        apartment="6-601",
    )
    service = DeviceService(
        user_service,
        database_url=f"sqlite+aiosqlite:///{(tmp_path / 'device-unbind-self.db').as_posix()}",
    )
    first = service.register_device(
        DeviceRegisterRequest(
            mac_address="54:10:26:01:00:31",
            device_name="T10-WATCH-A",
            user_id=elder.id,
            ingest_mode=DeviceIngestMode.SERIAL,
        )
    )
    second = service.register_device(
        DeviceRegisterRequest(
            mac_address="54:10:26:01:00:32",
            device_name="T10-WATCH-B",
            user_id=elder.id,
            ingest_mode=DeviceIngestMode.SERIAL,
        )
    )
    service.set_active_serial_target(first.mac_address)

    monkeypatch.setattr(device_api, "get_device_service", lambda: service)
    monkeypatch.setattr(
        device_api,
        "get_care_service",
        lambda: SimpleNamespace(
            get_directory=lambda: SimpleNamespace(
                elders=[
                    SimpleNamespace(
                        id=elder.id,
                        device_mac=first.mac_address,
                        device_macs=[first.mac_address, second.mac_address],
                    )
                ]
            )
        ),
    )
    monkeypatch.setattr(
        device_api,
        "require_session_user",
        lambda _authorization: SessionUser(
            id=elder.id,
            username="elder-unbind-self",
            name="解绑自测老人",
            role=UserRole.ELDER,
            community_id="C10001",
        ),
    )

    result = asyncio.run(device_api.unbind_device_self(authorization="Bearer demo-token"))

    assert result.device_id == first.id
    assert service.get_device(first.mac_address).bind_status == DeviceBindStatus.UNBOUND
    assert service.get_device(second.mac_address).bind_status == DeviceBindStatus.BOUND
