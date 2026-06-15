from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timezone

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

logger = logging.getLogger(__name__)
_serial_logger = logging.getLogger("serial_runtime")

from backend.api.alarm_api import router as alarm_router
from backend.api.agent_api import router as agent_router
from backend.api.auth_api import router as auth_router
from backend.api.care_api import router as care_router
from backend.api.camera_api import router as camera_router
from backend.api.camera_source_api import router as camera_source_router
from backend.api.chat_api import router as chat_router
from backend.api.device_api import router as device_router
from backend.api.health_api import router as health_router
from backend.api.model_finetune_api import router as model_finetune_router
from backend.api.relation_api import router as relation_router
from backend.api.target_user_api import router as target_user_router
from backend.api.user_api import router as user_router
from backend.api.video_bridge_api import router as video_bridge_router
from backend.api.vision_api import router as vision_router
from backend.api.voice_api import router as voice_router
from backend.api.omni_api import router as omni_router
from backend.config import get_settings
from backend.models.device_model import DeviceIngestMode, DeviceStatus
from backend.dependencies import (
    ensure_demo_overlay_history_window,
    get_alarm_service,
    get_camera_audio_hub,
    get_camera_frame_hub,
    get_camera_processed_frame_hub,
    get_video_bridge_service,
    get_data_generator,
    get_demo_data_status,
    get_device_service,
    get_parser,
    get_settings_dependency,
    get_websocket_manager,
    ingest_sample,
    publish_next_demo_overlay_sample,
    refresh_demo_overlay_samples,
)
from iot.mqtt_listener import MQTTGatewayListener
from iot.serial_reader import SerialGatewayReader


settings = get_settings()

_active_mock_watchers: dict[str, int] = defaultdict(int)
_active_mock_lock = asyncio.Lock()


async def _update_mock_watcher(device_mac: str, delta: int) -> None:
    normalized = device_mac.strip().upper()
    if not normalized:
        return
    async with _active_mock_lock:
        current = _active_mock_watchers.get(normalized, 0) + delta
        if current <= 0:
            _active_mock_watchers.pop(normalized, None)
        else:
            _active_mock_watchers[normalized] = current


async def _list_active_mock_macs() -> list[str]:
    async with _active_mock_lock:
        return [mac for mac, count in _active_mock_watchers.items() if count > 0]


async def _vision_service_pull_loop() -> None:
    service = get_video_bridge_service()
    while True:
        if service.poll_enabled():
            await service.poll_once_async()
        await asyncio.sleep(service.current_poll_interval_seconds())


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    # 启动即保证虚拟设备至少有 24h 可分析历史
    ensure_demo_overlay_history_window(hours=24, step_minutes=10)
    tasks: list[asyncio.Task] = []
    if settings.mock_runtime_enabled:
        tasks.append(asyncio.create_task(_mock_stream_loop()))
    elif settings.enable_mock_overlay:
        tasks.append(asyncio.create_task(_demo_overlay_stream_loop()))
    if settings.serial_runtime_enabled:
        tasks.append(asyncio.create_task(_serial_stream_loop()))
    if settings.data_mode == "mqtt" and settings.mqtt_enabled:
        tasks.append(asyncio.create_task(_mqtt_stream_loop()))
    if settings.vision_service_poll_enabled:
        tasks.append(asyncio.create_task(_vision_service_pull_loop()))
    app.state.background_tasks = tasks
    try:
        yield
    finally:
        with suppress(Exception):
            await get_camera_audio_hub().shutdown()
        for task in tasks:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    debug=settings.debug,
    summary="AIoT elder-care monitoring backend for the 2026 competition project.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(device_router, prefix=settings.api_v1_prefix)
app.include_router(user_router, prefix=settings.api_v1_prefix)
app.include_router(relation_router, prefix=settings.api_v1_prefix)
app.include_router(target_user_router, prefix=settings.api_v1_prefix)
app.include_router(health_router, prefix=settings.api_v1_prefix)
app.include_router(alarm_router, prefix=settings.api_v1_prefix)
app.include_router(agent_router, prefix=settings.api_v1_prefix)
app.include_router(chat_router, prefix=settings.api_v1_prefix)
app.include_router(care_router, prefix=settings.api_v1_prefix)
app.include_router(camera_router, prefix=settings.api_v1_prefix)
app.include_router(camera_source_router, prefix=settings.api_v1_prefix)
app.include_router(voice_router, prefix=settings.api_v1_prefix)
app.include_router(omni_router, prefix=settings.api_v1_prefix)
app.include_router(auth_router, prefix=settings.api_v1_prefix)
app.include_router(video_bridge_router, prefix=settings.api_v1_prefix)
app.include_router(vision_router, prefix=settings.api_v1_prefix)
app.include_router(model_finetune_router, prefix=settings.api_v1_prefix)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok", "app": settings.app_name}


@app.get("/api/v1/system/info")
async def system_info() -> dict[str, object]:
    cfg = get_settings_dependency()
    active_target = get_device_service().get_active_serial_target()
    active_target_mac = active_target.mac_address if active_target else None
    active_target_name = active_target.device_name if active_target else None
    return {
        "runtime_mode": cfg.runtime_mode,
        "bootstrap_source": cfg.bootstrap_source,
        "bootstrap_status": cfg.bootstrap_status,
        "bootstrap_reason": cfg.bootstrap_reason,
        "competition_stack": {
            "python": "3.9+",
            "anaconda": "22.9.0",
            "ollama": "0.12.9",
            "approved_local_models": ["qwen3:1.7b", "deepseek-r1:1.5b"],
            "database": "PostgreSQL 15 / TimescaleDB",
        },
        "configured": {
            "data_mode": cfg.data_mode,
            "runtime_mode": cfg.runtime_mode,
            "mock_mode": cfg.mock_runtime_enabled,
            "mock_overlay_enabled": cfg.enable_mock_overlay,
            "serial_mode": cfg.serial_runtime_enabled,
            "mqtt_mode": cfg.data_mode == "mqtt" and cfg.mqtt_enabled,
            "mac_prefixes": cfg.allowed_mac_prefixes,
            "offline_only_runtime": cfg.offline_only_runtime,
            "llm_provider": cfg.llm_provider,
            "preferred_llm_provider": cfg.preferred_llm_provider,
            "default_agent_provider": "qwen",
            "qwen_configured": cfg.qwen_llm_configured,
            "qwen_missing_config_fields": cfg.qwen_missing_config_fields,
            "qwen_model": cfg.qwen_model,
            "local_model_routing": cfg.local_model_routing,
            "local_default_model": cfg.local_default_model,
            "strict_source_match": cfg.strict_source_match,
            "target_user_vision_warmup_enabled": cfg.target_user_vision_warmup_enabled,
            "vision_service_poll_enabled": cfg.vision_service_poll_enabled,
            "fall_detection_enabled": cfg.fall_detection_enabled,
            "pose_detection_enabled": cfg.pose_detection_enabled,
        },
        "serial_runtime": {
            "enabled": cfg.serial_runtime_enabled,
            "port": cfg.serial_port or "auto-detect",
            "dual_collector_enabled": cfg.serial_dual_collector_enabled,
            "broadcast_port": cfg.serial_broadcast_port or None,
            "response_port": cfg.serial_response_port or None,
            "baudrate": cfg.serial_baudrate,
            "collection_strategy": cfg.serial_collection_strategy,
            "packet_type": cfg.serial_packet_type,
            "mac_filter": cfg.serial_mac_filter,
            "auto_configure": cfg.serial_auto_configure,
            "broadcast_sos_overlay": cfg.serial_enable_broadcast_sos_overlay,
            "response_cycle_seconds": cfg.serial_response_cycle_seconds,
            "broadcast_cycle_seconds": cfg.serial_broadcast_cycle_seconds,
            "command_delay_seconds": cfg.serial_command_delay_seconds,
            "active_target_mac": active_target_mac,
            "active_target_device_name": active_target_name,
            "target_locked": active_target_mac is not None,
            "merge_mode": "wait_for_ab",
            "runtime_mode": cfg.runtime_mode,
            "bootstrap_source": cfg.bootstrap_source,
            "bootstrap_status": cfg.bootstrap_status,
            "bootstrap_reason": cfg.bootstrap_reason,
        },
        "vision_runtime": {
            "base_url": cfg.vision_service_base_url,
            "camera_id": cfg.vision_service_camera_id,
            "poll_enabled": cfg.vision_service_poll_enabled,
            "poll_hz": cfg.vision_service_poll_hz,
            "timeout_seconds": cfg.vision_service_timeout_seconds,
        },
        "fall_runtime": {
            "enabled": cfg.fall_detection_enabled,
            "model_root": cfg.fall_detection_model_root,
            "target_device_mac": cfg.resolved_fall_detection_target_device_mac,
            "target_family_ids": cfg.resolved_fall_detection_target_family_ids,
        },
        "demo_data": get_demo_data_status(),
    }


@app.get("/api/v1/system/demo-data/status")
async def demo_data_status() -> dict[str, object]:
    return get_demo_data_status()


@app.post("/api/v1/system/demo-data/refresh")
async def refresh_demo_data() -> dict[str, object]:
    refresh_summary = refresh_demo_overlay_samples()
    return {
        "status": "ok",
        "message": "community sample window refreshed",
        "refresh_summary": refresh_summary,
        "data": get_demo_data_status(),
    }


@app.websocket("/ws/health/{device_mac}")
async def health_stream(device_mac: str, websocket: WebSocket) -> None:
    manager = get_websocket_manager()
    normalized_mac = device_mac.strip().upper()
    device = get_device_service().get_device(normalized_mac)
    is_mock_device = bool(device and device.ingest_mode == DeviceIngestMode.MOCK)
    await manager.connect_health(normalized_mac, websocket)
    if is_mock_device:
        await _update_mock_watcher(normalized_mac, 1)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await manager.disconnect_health(normalized_mac, websocket)
    finally:
        if is_mock_device:
            await _update_mock_watcher(normalized_mac, -1)


@app.websocket("/ws/alarms")
async def alarm_stream(websocket: WebSocket) -> None:
    manager = get_websocket_manager()
    await manager.connect_alarm(websocket)
    try:
        await websocket.send_json(
            {
                "type": "alarm_queue",
                "queue": [item.model_dump(mode="json") for item in get_alarm_service().queue_items(active_only=True)],
                "snapshot": get_alarm_service().queue_snapshot(),
            }
        )
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await manager.disconnect_alarm(websocket)


@app.websocket("/ws/camera")
async def camera_frame_stream(websocket: WebSocket) -> None:
    hub = get_camera_frame_hub()
    await hub.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await hub.disconnect(websocket)
    finally:
        await hub.disconnect(websocket)


@app.websocket("/ws/camera/processed")
async def camera_processed_frame_stream(websocket: WebSocket) -> None:
    hub = get_camera_processed_frame_hub()
    await hub.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await hub.disconnect(websocket)
    finally:
        await hub.disconnect(websocket)


@app.websocket("/ws/camera/audio/listen")
async def camera_audio_stream(websocket: WebSocket) -> None:
    hub = get_camera_audio_hub()
    await hub.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await hub.disconnect(websocket)
    finally:
        await hub.disconnect(websocket)


async def _mock_stream_loop() -> None:
    generator = get_data_generator()
    device_service = get_device_service()
    while True:
        now = datetime.now(timezone.utc)
        for persona in generator.personas:
            device = device_service.get_device(persona.mac_address)
            if device and device.status == DeviceStatus.OFFLINE:
                continue
            sample = generator.sample_for_device(persona.mac_address, now=now)
            await ingest_sample(sample)
        await asyncio.sleep(settings.mock_push_interval_seconds)


async def _demo_overlay_stream_loop() -> None:
    last_history_ensure = 0.0
    while True:
        active_mock_macs = await _list_active_mock_macs()
        if active_mock_macs:
            generator = get_data_generator()
            now = datetime.now(timezone.utc)
            device_service = get_device_service()
            for mac in active_mock_macs:
                device = device_service.get_device(mac)
                if not device or device.status == DeviceStatus.OFFLINE:
                    continue
                sample = generator.sample_for_device(mac, now=now)
                await ingest_sample(sample)

        publish_next_demo_overlay_sample()
        now_monotonic = asyncio.get_running_loop().time()
        # 每小时补齐一次，保证数据库中始终有至少一天 mock 历史
        if now_monotonic - last_history_ensure >= 3600:
            ensure_demo_overlay_history_window(hours=24, step_minutes=10)
            last_history_ensure = now_monotonic
        await asyncio.sleep(settings.mock_push_interval_seconds)


async def _serial_stream_loop() -> None:
    loop = asyncio.get_running_loop()
    reader = SerialGatewayReader(get_parser())

    def publish_from_thread(sample):
        _serial_logger.info(
            'Serial sample: mac=%s type=%s hr=%s spo2=%s temp=%s steps=%s bp=%s sos=%s',
            sample.device_mac,
            sample.packet_type,
            sample.heart_rate,
            sample.blood_oxygen,
            sample.temperature,
            sample.steps,
            sample.blood_pressure,
            sample.sos_flag,
        )
        if sample.sos_flag:
            _serial_logger.warning(
                '🚨 SOS DETECTED from %s (trigger=%s, value=%s, type=%s) — forwarding to ingest immediately',
                sample.device_mac,
                sample.sos_trigger,
                sample.sos_value,
                sample.packet_type,
            )
        future = asyncio.run_coroutine_threadsafe(ingest_sample(sample), loop)
        # Fire-and-forget: do NOT block the serial reader thread.
        # Attach an error callback so ingestion failures are logged
        # without stalling the serial data pipeline.
        def _on_done(fut):
            exc = fut.exception()
            if exc:
                _serial_logger.error("Ingest failed for %s: %s", sample.device_mac, exc)
        future.add_done_callback(_on_done)

    await asyncio.to_thread(
        reader.run,
        port=settings.serial_port or None,
        baudrate=settings.serial_baudrate,
        collection_strategy=settings.serial_collection_strategy,
        packet_type=settings.serial_packet_type,
        mac_filter=settings.serial_mac_filter,
        detection_keywords=settings.serial_detection_keywords,
        fallback_device_mac=settings.serial_fallback_device_mac or None,
        auto_configure=settings.serial_auto_configure,
        disable_uuid_output=settings.serial_disable_uuid_output,
        apply_mac_filter=settings.serial_apply_mac_filter,
        apply_packet_type=settings.serial_apply_packet_type,
        enable_broadcast_sos_overlay=settings.serial_enable_broadcast_sos_overlay,
        response_cycle_seconds=settings.serial_response_cycle_seconds,
        broadcast_cycle_seconds=settings.serial_broadcast_cycle_seconds,
        command_delay_seconds=settings.serial_command_delay_seconds,
        target_mac_provider=lambda: get_device_service().get_active_serial_target_mac(),
        on_sample=publish_from_thread,
    )


async def _mqtt_stream_loop() -> None:
    loop = asyncio.get_running_loop()
    listener = MQTTGatewayListener(get_parser())

    def publish_from_thread(sample):
        future = asyncio.run_coroutine_threadsafe(ingest_sample(sample), loop)
        future.result()

    await asyncio.to_thread(
        listener.run,
        settings.mqtt_broker_host,
        settings.mqtt_broker_port,
        settings.mqtt_topic,
        username=settings.mqtt_username or None,
        password=settings.mqtt_password or None,
        keepalive_seconds=settings.mqtt_keepalive_seconds,
        on_sample=publish_from_thread,
    )
