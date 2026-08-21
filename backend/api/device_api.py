from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException

from backend.dependencies import (
    get_alarm_service,
    get_device_service,
    get_health_data_repository,
    get_websocket_manager,
    require_session_user,
    require_write_session_user,
)
from backend.models.auth_model import SessionUser
from backend.models.device_bind_model import (
    DeviceBindLogRecord,
    DeviceBindRequest,
    DeviceRebindRequest,
    DeviceSelfBindRequest,
    DeviceUnbindRequest,
)
from backend.models.device_model import (
    DeviceBindStatus,
    DeviceIngestMode,
    DeviceRecord,
    DeviceRegisterRequest,
    SerialTargetSwitchRequest,
    SerialTargetSwitchResponse,
)
from datetime import datetime, timezone
from backend.models.user_model import UserRole


router = APIRouter(prefix="/devices", tags=["devices"])


async def _clear_device_sos_guard(mac_address: str) -> None:
    alarm_service = get_alarm_service()
    cleared_alarm_ids = alarm_service.clear_device_sos_state(mac_address)
    if not cleared_alarm_ids:
        return
    repository = get_health_data_repository()
    for alarm_id in cleared_alarm_ids:
        repository.acknowledge_alert(alarm_id)
    await get_websocket_manager().broadcast_alarm_queue(
        {
            "type": "alarm_queue",
            "queue": [item.model_dump(mode="json") for item in alarm_service.queue_items(active_only=True)],
            "snapshot": alarm_service.queue_snapshot(),
        }
    )


def _require_writer(authorization: str | None) -> SessionUser:
    try:
        return require_write_session_user(authorization)
    except ValueError as exc:
        code = str(exc)
        if code in {"AUTH_REQUIRED", "INVALID_SESSION"}:
            raise HTTPException(status_code=401, detail=code) from exc
        raise HTTPException(status_code=403, detail=code) from exc


def _require_authenticated_user(authorization: str | None) -> SessionUser:
    try:
        return require_session_user(authorization)
    except ValueError as exc:
        code = str(exc)
        raise HTTPException(status_code=401 if code in {"AUTH_REQUIRED", "INVALID_SESSION"} else 403, detail=code) from exc


@router.get("", response_model=list[DeviceRecord])
async def list_devices() -> list[DeviceRecord]:
    return get_device_service().list_devices()


@router.get("/{mac_address}", response_model=DeviceRecord)
async def get_device(mac_address: str) -> DeviceRecord:
    device = get_device_service().get_device(mac_address)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    return device


@router.get("/{mac_address}/bind-logs", response_model=list[DeviceBindLogRecord])
async def list_device_bind_logs(mac_address: str) -> list[DeviceBindLogRecord]:
    return get_device_service().list_bind_logs(mac_address)


@router.post("/register", response_model=DeviceRecord)
async def register_device(payload: DeviceRegisterRequest, authorization: str | None = Header(default=None)) -> DeviceRecord:
    operator = _require_writer(authorization)
    try:
        return get_device_service().register_device(payload, operator_id=operator.id)
    except ValueError as exc:
        code = str(exc)
        if code == "DEVICE_ALREADY_EXISTS":
            raise HTTPException(status_code=409, detail=code) from exc
        if code == "TARGET_USER_ALREADY_HAS_DEVICE_OF_SAME_MODEL":
            raise HTTPException(status_code=409, detail=code) from exc
        if code == "USER_NOT_FOUND":
            raise HTTPException(status_code=404, detail=code) from exc
        raise HTTPException(status_code=400, detail=code) from exc


@router.post("/bind", response_model=DeviceBindLogRecord)
async def bind_device(payload: DeviceBindRequest, authorization: str | None = Header(default=None)) -> DeviceBindLogRecord:
    _require_writer(authorization)
    try:
        await _clear_device_sos_guard(payload.mac_address)
        result = get_device_service().bind_device(payload)
        return result
    except ValueError as exc:
        code = str(exc)
        if code in {"DEVICE_NOT_FOUND", "USER_NOT_FOUND"}:
            raise HTTPException(status_code=404, detail=code) from exc
        if code in {"DEVICE_ALREADY_BOUND", "DEVICE_ALREADY_BOUND_TO_TARGET", "TARGET_USER_ALREADY_HAS_DEVICE_OF_SAME_MODEL"}:
            raise HTTPException(status_code=409, detail=code) from exc
        raise HTTPException(status_code=400, detail=code) from exc


@router.post("/unbind", response_model=DeviceBindLogRecord)
async def unbind_device(payload: DeviceUnbindRequest, authorization: str | None = Header(default=None)) -> DeviceBindLogRecord:
    _require_writer(authorization)
    try:
        result = get_device_service().unbind_device(payload)
        await _clear_device_sos_guard(payload.mac_address)
        return result
    except ValueError as exc:
        code = str(exc)
        if code == "DEVICE_NOT_FOUND":
            raise HTTPException(status_code=404, detail=code) from exc
        if code == "DEVICE_NOT_BOUND":
            raise HTTPException(status_code=409, detail=code) from exc
        raise HTTPException(status_code=400, detail=code) from exc


@router.post("/unbind/self", response_model=DeviceBindLogRecord)
async def unbind_device_self(authorization: str | None = Header(default=None)) -> DeviceBindLogRecord:
    """Elder self-service: unbind the real serial device currently bound to the calling elder."""
    from backend.dependencies import get_care_service

    user = _require_authenticated_user(authorization)

    directory = get_care_service().get_directory()

    if user.role == UserRole.ELDER:
        elder = next((item for item in directory.elders if item.id == user.id), None)
        if elder is None:
            raise HTTPException(status_code=404, detail="ELDER_PROFILE_NOT_FOUND")
        elder_macs = set(
            mac.upper()
            for mac in (elder.device_macs or ([elder.device_mac] if elder.device_mac else []))
            if mac
        )
    else:
        elder_ids = {
            e.id for e in directory.elders
            if user.family_id and user.family_id in e.family_ids
        } or {e.id for e in directory.elders}
        elder_macs = set(
            mac.upper()
            for e in directory.elders if e.id in elder_ids
            for mac in (e.device_macs or ([e.device_mac] if e.device_mac else []))
            if mac
        )

    device_service = get_device_service()
    devices = device_service.list_devices()
    serial_candidates = [
        d
        for d in devices
        if d.ingest_mode == DeviceIngestMode.SERIAL
        and d.bind_status == DeviceBindStatus.BOUND
        and (d.user_id == user.id or d.mac_address.upper() in elder_macs)
    ]
    if not serial_candidates:
        raise HTTPException(status_code=404, detail="NO_BOUND_SERIAL_DEVICE")

    active_target_mac = (device_service.get_active_serial_target_mac() or "").upper()
    serial_device = next(
        (d for d in serial_candidates if d.mac_address.upper() == active_target_mac),
        None,
    )
    if serial_device is None:
        serial_device = sorted(
            serial_candidates,
            key=lambda d: (
                d.last_seen_at or d.created_at,
                d.created_at,
                d.mac_address,
            ),
        )[-1]

    payload = DeviceUnbindRequest(
        mac_address=serial_device.mac_address,
        operator_id=user.id,
        reason="elder_self_unbind",
    )
    try:
        result = get_device_service().unbind_device(payload)
        await _clear_device_sos_guard(payload.mac_address)
        return result
    except ValueError as exc:
        code = str(exc)
        if code == "DEVICE_NOT_FOUND":
            raise HTTPException(status_code=404, detail=code) from exc
        raise HTTPException(status_code=400, detail=code) from exc


@router.post("/bind/self", response_model=DeviceRecord)
async def bind_device_self(
    payload: DeviceSelfBindRequest,
    authorization: str | None = Header(default=None),
) -> DeviceRecord:
    user = _require_authenticated_user(authorization)
    if user.role != UserRole.ELDER:
        raise HTTPException(status_code=403, detail="SELF_BIND_FOR_ELDER_ONLY")

    device_service = get_device_service()
    existing = device_service.get_device(payload.mac_address)

    try:
        if existing is None:
            await _clear_device_sos_guard(payload.mac_address)
            register_payload: dict[str, object] = {
                "mac_address": payload.mac_address,
                "device_name": (payload.device_name or "T10-WATCH").strip() or "T10-WATCH",
                "model_code": payload.model_code,
                "ingest_mode": payload.ingest_mode,
                "user_id": user.id,
            }
            if payload.service_uuid:
                register_payload["service_uuid"] = payload.service_uuid
            if payload.device_uuid:
                register_payload["device_uuid"] = payload.device_uuid
            created = device_service.register_device(
                DeviceRegisterRequest(**register_payload),
                operator_id=user.id,
            )
            return created

        if existing.user_id == user.id and existing.bind_status == DeviceBindStatus.BOUND:
            await _clear_device_sos_guard(existing.mac_address)
            if existing.ingest_mode == DeviceIngestMode.SERIAL:
                try:
                    device_service.set_active_serial_target(existing.mac_address)
                except ValueError:
                    pass
            return existing

        await _clear_device_sos_guard(existing.mac_address)
        device_service.bind_device(
            DeviceBindRequest(
                mac_address=existing.mac_address,
                target_user_id=user.id,
                operator_id=user.id,
                new_ingest_mode=payload.ingest_mode,
            )
        )
        bound = device_service.get_device(existing.mac_address)
        if bound is None:
            raise HTTPException(status_code=404, detail="DEVICE_NOT_FOUND")
        if bound.ingest_mode == DeviceIngestMode.SERIAL:
            try:
                device_service.set_active_serial_target(bound.mac_address)
            except ValueError:
                pass
        return bound
    except ValueError as exc:
        code = str(exc)
        if code in {"DEVICE_NOT_FOUND", "USER_NOT_FOUND"}:
            raise HTTPException(status_code=404, detail=code) from exc
        if code in {"DEVICE_ALREADY_BOUND", "DEVICE_ALREADY_BOUND_TO_TARGET", "TARGET_USER_ALREADY_HAS_DEVICE_OF_SAME_MODEL"}:
            raise HTTPException(status_code=409, detail=code) from exc
        raise HTTPException(status_code=400, detail=code) from exc


@router.post("/rebind", response_model=DeviceBindLogRecord)
async def rebind_device(payload: DeviceRebindRequest, authorization: str | None = Header(default=None)) -> DeviceBindLogRecord:
    _require_writer(authorization)
    try:
        await _clear_device_sos_guard(payload.mac_address)
        result = get_device_service().rebind_device(payload)
        return result
    except ValueError as exc:
        code = str(exc)
        if code in {"DEVICE_NOT_FOUND", "USER_NOT_FOUND"}:
            raise HTTPException(status_code=404, detail=code) from exc
        if code in {"DEVICE_ALREADY_BOUND_TO_TARGET", "TARGET_USER_ALREADY_HAS_DEVICE_OF_SAME_MODEL"}:
            raise HTTPException(status_code=409, detail=code) from exc
        raise HTTPException(status_code=400, detail=code) from exc


@router.delete("/{mac_address}", response_model=DeviceRecord)
async def delete_device(mac_address: str, authorization: str | None = Header(default=None)) -> DeviceRecord:
    _require_writer(authorization)
    try:
        return get_device_service().delete_device(mac_address)
    except ValueError as exc:
        code = str(exc)
        if code == "DEVICE_NOT_FOUND":
            raise HTTPException(status_code=404, detail=code) from exc
        raise HTTPException(status_code=400, detail=code) from exc


@router.post("/serial-target", response_model=SerialTargetSwitchResponse)
async def switch_serial_target(
    payload: SerialTargetSwitchRequest,
    authorization: str | None = Header(default=None),
) -> SerialTargetSwitchResponse:
    _require_writer(authorization)
    switched_at = datetime.now(timezone.utc)
    try:
        active_target, previous_target_mac = get_device_service().set_active_serial_target(payload.mac_address)
    except ValueError as exc:
        code = str(exc)
        if code == "DEVICE_NOT_FOUND":
            raise HTTPException(status_code=404, detail=code) from exc
        if code in {"DEVICE_NOT_SERIAL", "DEVICE_DISABLED"}:
            raise HTTPException(status_code=409, detail=code) from exc
        raise HTTPException(status_code=400, detail=code) from exc

    return SerialTargetSwitchResponse(
        active_target_mac=active_target.mac_address,
        active_target_device_name=active_target.device_name,
        previous_target_mac=previous_target_mac,
        switched_at=switched_at,
    )
