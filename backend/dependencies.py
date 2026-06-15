from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from agent.analysis_service import HealthDataAnalysisService
from agent.context_assembler import AgentContextAssembler
from agent.langchain_rag_service import LangChainRAGService
from agent.langgraph_health_agent import HealthAgentService
from agent.mcp_adapter import LocalToolAdapter
from agent.model_interfaces import (
    AgentModelSuite,
    RuleBasedAlarmInterpretationModel,
    RuleBasedCareSuggestionModel,
    RuleBasedHealthAssessmentModel,
    RuleBasedRiskScoringModel,
    ServiceBackedAnomalyExplainModel,
)
from ai.anomaly_detector import CommunityHealthClusterer, IntelligentAnomalyScorer, RealtimeAnomalyDetector
from ai.data_generator import SyntheticHealthDataGenerator
from ai.health_score_model import BaselineTracker, HealthScoreService as DemoHealthScoreService
from backend.config import get_settings
from backend.models.auth_model import SessionUser
from backend.models.alarm_model import AlarmLayer, AlarmPriority, AlarmRecord, AlarmType
from backend.models.device_model import DeviceIngestMode, DeviceRecord, DeviceStatus, ingest_source_matches_mode
from backend.models.health_model import HealthSample, IngestResponse, IngestionSource
from backend.models.analytics_model import AgentElderSubject, WindowKind
from backend.models.user_model import UserRole
from backend.ml.inference import HealthInferenceEngine
from backend.repositories.score_repo import ScoreRepository
from backend.repositories.mobile_push_device_repo import MobilePushDeviceRepository
from backend.repositories.warning_repo import WarningRepository
from backend.repositories.wearable_repo import WearableRepository
from backend.services.alarm_priority_queue import AlarmPriorityQueue
from backend.services.alarm_service import AlarmService
from backend.services.camera_audio_hub import CameraAudioHub
from backend.services.camera_setup_config_service import CameraSetupConfigService
from backend.services.camera_source_registry import CameraSourceRegistry
from backend.services.camera_stream_hub import CameraDetectionFrameHub, CameraFrameHub, CameraPoseFrameHub, CombinedProcessedFrameHub
from backend.services.community_insight_service import CommunityInsightService
from backend.services.care_service import CareService
from backend.services.device_service import DeviceService
from backend.services.explanation_service import ExplanationService
from backend.services.health_data_repository import HealthDataRepository
from backend.services.health_score_service import HealthScoreService as StructuredHealthScoreService
from backend.services.health_stability_service import HealthStabilityService
from backend.services.model_finetune_service import ModelFinetuneService
from backend.services.notification_service import NotificationService
from backend.services.optional_reid_embedding_service import OptionalReidEmbeddingService
from backend.services.posture_event_service import PostureEventService
from backend.services.posture_knowledge_service import PostureKnowledgeService
from backend.services.relation_service import RelationService
from backend.services.stream_service import StreamService
from backend.services.external_camera_bridge_service import ExternalCameraBridgeService
from backend.services.fall_frame_test_service import FallFrameTestService
from backend.services.target_pose_service import TargetPoseService
from backend.services.target_user_fall_service import TargetUserFallService
from backend.services.target_user_service import TargetUserService
from backend.services.user_service import UserService
from backend.services.video_adapter import VideoAnalysisAdapter
from backend.services.video_bridge_service import VideoBridgeService
from backend.services.warning_service import WarningService
from backend.services.websocket_manager import WebSocketManager
from backend.schemas.health import VitalSignsPayload
from iot.parser import T10PacketParser


logger = logging.getLogger(__name__)
_settings = get_settings()
_user_service = UserService()
_relation_service = RelationService(_user_service)
_device_service = DeviceService(_user_service, database_url=_settings.database_url)
_stream_service = StreamService(retention_points=_settings.stream_retention_points)
_websocket_manager = WebSocketManager()
_alarm_priority_queue = AlarmPriorityQueue(redis_url=_settings.redis_url)
_notification_service = NotificationService()
_health_data_repository = HealthDataRepository(database_url=_settings.database_url)
_realtime_detector = RealtimeAnomalyDetector(
    window_size=_settings.realtime_window_size,
    zscore_threshold=_settings.zscore_threshold,
)
_alarm_service = AlarmService(
    detector=_realtime_detector,
    queue=_alarm_priority_queue,
    notification_service=_notification_service,
    sos_dedupe_window_seconds=_settings.sos_broadcast_window_seconds,
)
_baseline_tracker = BaselineTracker()
_health_score_service = DemoHealthScoreService(floor=_settings.health_score_floor)
_community_clusterer = CommunityHealthClusterer()
_intelligent_scorer = IntelligentAnomalyScorer()
_data_generator = SyntheticHealthDataGenerator(
    device_count=_settings.mock_device_count,
    mac_prefix=(_settings.allowed_mac_prefixes[0] if _settings.allowed_mac_prefixes else _settings.mock_device_mac_prefix),
)
_parser = T10PacketParser(
    sos_window_seconds=_settings.sos_broadcast_window_seconds,
    merge_timeout_seconds=max(0.3, _settings.serial_packet_merge_timeout_seconds),
)
_analysis_service = HealthDataAnalysisService()
_rag_service = LangChainRAGService(_settings, _settings.data_dir.parent / "docs" / "knowledge-base")
_care_service = CareService(_device_service, _user_service, _relation_service, _settings)
_agent_context_assembler = AgentContextAssembler(
    _stream_service,
    _alarm_service,
    _device_service,
    _care_service,
)
_agent_tool_adapter = LocalToolAdapter()
_agent_tool_adapter.register_tool(name="get_device_realtime", description="Query realtime health sample for a single device", handler=lambda call: _tool_get_device_realtime(call.payload))
_agent_tool_adapter.register_tool(name="get_device_trend", description="Query recent trend points for a single device", handler=lambda call: _tool_get_device_trend(call.payload))
_agent_tool_adapter.register_tool(name="get_device_status", description="Query device ledger, online state and bind state", handler=lambda call: _tool_get_device_status(call.payload))
_agent_tool_adapter.register_tool(name="get_device_bind_history", description="Query device bind history", handler=lambda call: _tool_get_device_bind_history(call.payload))
_agent_tool_adapter.register_tool(name="get_elder_profile", description="Query elder profile with device and family relations", handler=lambda call: _tool_get_elder_profile(call.payload))
_agent_tool_adapter.register_tool(name="get_family_relations", description="Query elder-family relations", handler=lambda call: _tool_get_family_relations(call.payload))
_agent_tool_adapter.register_tool(name="get_active_alarms", description="Query active alarms", handler=lambda call: _tool_get_active_alarms(call.payload))
_agent_tool_adapter.register_tool(name="get_community_overview", description="Query community monitoring overview", handler=lambda call: _tool_get_community_overview(call.payload))
_agent_tool_adapter.register_tool(name="get_care_directory", description="Query care directory summary", handler=lambda call: _care_service.get_directory().model_dump(mode="json"))
_agent_tool_adapter.register_tool(name="weather_lookup", description="Reserved weather context lookup", source="external_placeholder", handler=lambda call: _tool_placeholder_external("weather_lookup", call.payload))
_agent_tool_adapter.register_tool(name="air_quality_lookup", description="Reserved air quality context lookup", source="external_placeholder", handler=lambda call: _tool_placeholder_external("air_quality_lookup", call.payload))
_agent_tool_adapter.register_tool(name="nearby_facility_lookup", description="Reserved nearby facility lookup", source="external_placeholder", handler=lambda call: _tool_placeholder_external("nearby_facility_lookup", call.payload))
_agent_tool_adapter.register_tool(name="holiday_lookup", description="Reserved holiday lookup", source="external_placeholder", handler=lambda call: _tool_holiday_lookup(call.payload))
_agent_tool_adapter.register_tool(name="run_tavily_search", description="Run external web search for complementary context", handler=lambda call: _community_insight_service.tool_run_tavily_search(call.payload))
_agent_tool_adapter.register_tool(name="generate_analysis_report", description="Generate structured analysis report", handler=lambda call: _tool_generate_analysis_report(call.payload))
_agent_model_suite = AgentModelSuite(
    health_assessment=RuleBasedHealthAssessmentModel(_analysis_service),
    risk_scoring=RuleBasedRiskScoringModel(),
    anomaly_explain=ServiceBackedAnomalyExplainModel(_intelligent_scorer, _community_clusterer),
    care_suggestion=RuleBasedCareSuggestionModel(),
    alarm_interpretation=RuleBasedAlarmInterpretationModel(),
)
_agent_service = HealthAgentService(
    _settings,
    _rag_service,
    _analysis_service,
    context_assembler=_agent_context_assembler,
    tool_adapter=_agent_tool_adapter,
    model_suite=_agent_model_suite,
)
_explanation_service = ExplanationService()
_community_insight_service = CommunityInsightService(
    settings=_settings,
    analysis_service=_analysis_service,
    stream_service=_stream_service,
    alarm_service=_alarm_service,
    device_service=_device_service,
    care_service=_care_service,
    rag_service=_rag_service,
    repository=_health_data_repository,
)
_structured_inference_engine = HealthInferenceEngine(_settings)
_structured_stability_service = HealthStabilityService(_settings)
_wearable_repo = WearableRepository(_settings.database_url)
_score_repo = ScoreRepository(_settings.database_url)
_warning_repo = WarningRepository(_settings.database_url)
_structured_health_score_service = StructuredHealthScoreService(
    inference_engine=_structured_inference_engine,
    wearable_repo=_wearable_repo,
    score_repo=_score_repo,
    warning_repo=_warning_repo,
    stability_service=_structured_stability_service,
)
_warning_service = WarningService(health_score_service=_structured_health_score_service)
_last_community_alarm_at: datetime | None = None
_mobile_push_device_repo: MobilePushDeviceRepository | None = None
_target_user_service: TargetUserService | None = None
_target_pose_service: TargetPoseService | None = None
_posture_event_service: PostureEventService | None = None
_posture_knowledge_service: PostureKnowledgeService | None = None
_target_user_fall_service: TargetUserFallService | None = None
_external_camera_bridge_service: ExternalCameraBridgeService | None = None
_video_bridge_service: VideoBridgeService | None = None
_model_finetune_service: ModelFinetuneService | None = None
_camera_frame_hub: CameraFrameHub | None = None
_camera_detection_frame_hub: CameraDetectionFrameHub | None = None
_camera_pose_frame_hub: CameraPoseFrameHub | None = None
_camera_processed_frame_hub: CombinedProcessedFrameHub | None = None
_camera_audio_hub: CameraAudioHub | None = None
_camera_source_registry: CameraSourceRegistry | None = None
_camera_setup_config_service: CameraSetupConfigService | None = None
_camera_source_frame_hubs: dict[str, CameraFrameHub] = {}
_camera_source_audio_hubs: dict[str, CameraAudioHub] = {}
_camera_source_processed_hubs: dict[str, CombinedProcessedFrameHub] = {}


# NOTE: ingest_sample is defined further below (after helper functions)
# to access all required services. See the async def ingest_sample(...)
# near the end of this module.

# 始终 seed mock 设备，用于 demo overlay 和 AI 模型预热
# serial/mqtt 模式下 mock 设备以 ingest_mode=mock 标记，与真实串口设备区分
# mock 设备直接设为 ONLINE，overlay 流会持续推数据，不依赖串口
_mock_devices_to_seed = _data_generator.build_devices()
for _mock_index, _mock_dev in enumerate(_mock_devices_to_seed):
    if _device_service.get_device(_mock_dev.mac_address) is None:
        _device_service.seed_devices([_mock_dev])
    # 李建国 (elder01_02) 的设备永远在线
    if _mock_dev.mac_address == "53:57:08:00:00:01":
        seeded_status = DeviceStatus.ONLINE
    else:
        seeded_status = DeviceStatus.OFFLINE if _mock_index % 5 == 0 else DeviceStatus.ONLINE
    _device_service.update_status(_mock_dev.mac_address, seeded_status)
_intelligent_scorer.warmup(_data_generator.build_training_sequences(hours=24, step_minutes=10))

if _settings.data_mode == "mock" and _settings.use_mock_data:
    # 纯 mock 模式：预填充历史数据到 stream，让 UI 启动即有数据
    for device_history in _data_generator.build_history(hours=1, step_minutes=10).values():
        for sample in device_history:
            baseline = _baseline_tracker.observe(sample)
            sample.health_score = _health_score_service.score(sample, baseline)
            _stream_service.publish(sample)


def get_device_service() -> DeviceService:
    return _device_service


def get_user_service() -> UserService:
    return _user_service


def get_relation_service() -> RelationService:
    return _relation_service


def get_stream_service() -> StreamService:
    return _stream_service


def get_alarm_service() -> AlarmService:
    return _alarm_service


def get_websocket_manager() -> WebSocketManager:
    return _websocket_manager


def get_health_data_repository() -> HealthDataRepository:
    return _health_data_repository


def get_data_generator() -> SyntheticHealthDataGenerator:
    return _data_generator


_demo_overlay_cycle_index = 0
_demo_overlay_last_published_at: datetime | None = None
_demo_overlay_last_refresh_at: datetime | None = None


def _eligible_demo_overlay_device_macs() -> list[str]:
    devices = _device_service.list_devices()
    eligible_device_macs = {
        device.mac_address
        for device in devices
        if device.status != DeviceStatus.OFFLINE
    }
    personas = getattr(_data_generator, "personas", None) or []
    eligible: list[str] = []
    for persona in personas:
        mac = str(getattr(persona, "mac_address", "")).strip().upper()
        if mac and mac in eligible_device_macs:
            eligible.append(mac)
    return eligible


def _sample_source_allowed(device: DeviceRecord, sample: HealthSample) -> bool:
    if not _settings.strict_source_match:
        return True
    effective_mode = get_effective_device_ingest_mode(device.mac_address, device.ingest_mode)
    return ingest_source_matches_mode(effective_mode, sample.source)


def _persist_demo_overlay_sample(sample: HealthSample, *, explanation: str, source_label: str) -> None:
    device = _device_service.get_device(sample.device_mac)
    if isinstance(device, DeviceRecord) and not _sample_source_allowed(device, sample):
        return
    _health_data_repository.persist_sample(sample)
    _stream_service.publish(sample)


def refresh_demo_overlay_samples() -> dict[str, object]:
    global _demo_overlay_last_refresh_at
    eligible = _eligible_demo_overlay_device_macs()
    for mac in eligible:
        sample = _data_generator.sample_for_device(mac)
        _persist_demo_overlay_sample(sample, explanation="community sample refresh", source_label="demo_overlay_refresh")
    _demo_overlay_last_refresh_at = datetime.now(timezone.utc)
    return {"device_count": len(eligible), "device_macs": eligible}


def publish_next_demo_overlay_sample() -> None:
    global _demo_overlay_cycle_index, _demo_overlay_last_published_at
    eligible = _eligible_demo_overlay_device_macs()
    if not eligible:
        return
    mac = eligible[_demo_overlay_cycle_index % len(eligible)]
    _demo_overlay_cycle_index = (_demo_overlay_cycle_index + 1) % len(eligible)
    sample = _data_generator.sample_for_device(mac)
    _persist_demo_overlay_sample(sample, explanation="community sample overlay", source_label="demo_overlay_tick")
    _demo_overlay_last_published_at = datetime.now(timezone.utc)


def get_demo_data_status() -> dict[str, object]:
    eligible = _eligible_demo_overlay_device_macs()
    return {
        "device_count": len(eligible),
        "device_macs": eligible,
        "last_refresh_at": _demo_overlay_last_refresh_at.isoformat() if _demo_overlay_last_refresh_at else None,
        "last_published_at": _demo_overlay_last_published_at.isoformat() if _demo_overlay_last_published_at else None,
    }


def ensure_demo_overlay_history_window(*, hours: int = 24, step_minutes: int = 10) -> dict[str, int]:
    """Ensure mock devices keep at least a rolling 24h history in DB."""
    eligible = _eligible_demo_overlay_device_macs()
    if not eligible:
        return {"devices_checked": 0, "devices_backfilled": 0, "inserted_samples": 0}

    now = datetime.now(timezone.utc)
    start_at = now - timedelta(hours=max(1, hours))
    expected_points = max(1, int((hours * 60) / max(1, step_minutes)))
    histories = _data_generator.build_history(hours=max(1, hours), step_minutes=max(1, step_minutes))

    devices_backfilled = 0
    inserted_samples = 0
    for mac in eligible:
        existing = _health_data_repository.list_samples(
            device_mac=mac,
            start_at=start_at,
            end_at=now,
            limit=max(expected_points * 3, 300),
        )
        if len(existing) >= expected_points:
            continue

        history_samples = histories.get(mac, [])
        if not history_samples:
            continue

        for sample in history_samples:
            baseline = _baseline_tracker.observe(sample)
            sample.health_score = _health_score_service.score(sample, baseline)
            _health_data_repository.persist_sample(sample)
            inserted_samples += 1
        devices_backfilled += 1

    return {
        "devices_checked": len(eligible),
        "devices_backfilled": devices_backfilled,
        "inserted_samples": inserted_samples,
    }


def get_settings_dependency():
    return _settings


def get_parser() -> T10PacketParser:
    return _parser


def get_agent_service() -> HealthAgentService:
    return _agent_service


def get_care_service() -> CareService:
    return _care_service


def get_explanation_service() -> ExplanationService:
    return _explanation_service


def get_community_insight_service() -> CommunityInsightService:
    return _community_insight_service


def get_demo_elder_subjects() -> list[AgentElderSubject]:
    directory = _care_service.get_demo_directory()
    subjects: list[AgentElderSubject] = []
    for elder in directory.elders:
        macs = list(getattr(elder, "device_macs", [])) or ([elder.device_mac] if elder.device_mac else [])
        subjects.append(
            AgentElderSubject(
                elder_id=elder.id,
                elder_name=elder.name,
                apartment=elder.apartment,
                device_macs=[mac for mac in macs if mac],
                has_realtime_device=bool(macs),
                risk_level="unknown",
                is_demo_subject=True,
            )
        )
    return subjects


def require_session_user(authorization: str | None) -> SessionUser:
    if not authorization:
        raise ValueError("AUTH_REQUIRED")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise ValueError("AUTH_REQUIRED")
    user = _care_service.resolve_session(token.strip())
    if not user:
        raise ValueError("INVALID_SESSION")
    return user


def require_write_session_user(authorization: str | None) -> SessionUser:
    user = require_session_user(authorization)
    if user.role not in {UserRole.FAMILY, UserRole.COMMUNITY, UserRole.ADMIN}:
        raise ValueError("FORBIDDEN")
    return user


def get_data_analysis_service() -> HealthDataAnalysisService:
    return _analysis_service


def get_intelligent_scorer() -> IntelligentAnomalyScorer:
    return _intelligent_scorer


def get_community_clusterer() -> CommunityHealthClusterer:
    return _community_clusterer


def get_score_repo() -> ScoreRepository:
    return _score_repo


def get_structured_health_score_service() -> StructuredHealthScoreService:
    return _structured_health_score_service


def get_warning_evaluation_service() -> WarningService:
    return _warning_service


def get_mobile_push_device_repo() -> MobilePushDeviceRepository:
    global _mobile_push_device_repo
    if _mobile_push_device_repo is None:
        _mobile_push_device_repo = MobilePushDeviceRepository(_settings.database_url)
    return _mobile_push_device_repo


def get_posture_event_service() -> PostureEventService:
    global _posture_event_service
    if _posture_event_service is None:
        _posture_event_service = PostureEventService()
    return _posture_event_service


def get_posture_knowledge_service() -> PostureKnowledgeService:
    global _posture_knowledge_service
    if _posture_knowledge_service is None:
        _posture_knowledge_service = PostureKnowledgeService(
            resources_root=_settings.data_dir.parent / "backend" / "resources"
        )
    return _posture_knowledge_service


def get_target_user_service() -> TargetUserService:
    global _target_user_service
    if _target_user_service is None:
        _target_user_service = TargetUserService(
            data_root=_settings.data_dir,
            model_root=Path(_settings.fall_detection_model_root),
        )
    return _target_user_service


def get_target_pose_service() -> TargetPoseService:
    global _target_pose_service
    if _target_pose_service is None:
        _target_pose_service = TargetPoseService(
            model_root=Path(_settings.fall_detection_model_root),
        )
    return _target_pose_service


def get_target_user_fall_service() -> TargetUserFallService:
    global _target_user_fall_service
    if _target_user_fall_service is None:
        _target_user_fall_service = TargetUserFallService(
            data_root=_settings.data_dir,
            model_root=Path(_settings.fall_detection_model_root),
            target_user_service=get_target_user_service(),
            target_pose_service=get_target_pose_service(),
            posture_event_service=get_posture_event_service(),
            posture_knowledge_service=get_posture_knowledge_service(),
        )
    return _target_user_fall_service


def get_external_camera_bridge_service() -> ExternalCameraBridgeService:
    global _external_camera_bridge_service
    if _external_camera_bridge_service is None:
        _external_camera_bridge_service = ExternalCameraBridgeService(
            data_root=_settings.data_dir,
            target_user_fall_service=get_target_user_fall_service(),
        )
    return _external_camera_bridge_service


def get_video_bridge_service() -> VideoBridgeService:
    global _video_bridge_service
    if _video_bridge_service is None:
        _video_bridge_service = VideoBridgeService(
            VideoAnalysisAdapter(),
            settings=_settings,
            alarm_ingest_callback=_ingest_video_bridge_alarm_event,
        )
    return _video_bridge_service


def get_model_finetune_service() -> ModelFinetuneService:
    global _model_finetune_service
    if _model_finetune_service is None:
        _model_finetune_service = ModelFinetuneService(project_root=_settings.data_dir.parent)
    return _model_finetune_service


def get_camera_frame_hub() -> CameraFrameHub:
    global _camera_frame_hub
    if _camera_frame_hub is None:
        _camera_frame_hub = CameraFrameHub(_settings)
    return _camera_frame_hub


def get_camera_detection_frame_hub() -> CameraDetectionFrameHub:
    global _camera_detection_frame_hub
    if _camera_detection_frame_hub is None:
        _camera_detection_frame_hub = CameraDetectionFrameHub(
            _settings,
            event_provider=lambda: None,
        )
    return _camera_detection_frame_hub


def get_camera_pose_frame_hub() -> CameraPoseFrameHub:
    global _camera_pose_frame_hub
    if _camera_pose_frame_hub is None:
        _camera_pose_frame_hub = CameraPoseFrameHub(
            _settings,
            payload_provider=lambda: None,
        )
    return _camera_pose_frame_hub


def get_camera_processed_frame_hub() -> CombinedProcessedFrameHub:
    global _camera_processed_frame_hub
    if _camera_processed_frame_hub is None:
        _camera_processed_frame_hub = CombinedProcessedFrameHub(
            _settings,
            pose_payload_provider=lambda: None,
            fall_payload_provider=lambda: None,
        )
    return _camera_processed_frame_hub


def get_camera_audio_hub() -> CameraAudioHub:
    global _camera_audio_hub
    if _camera_audio_hub is None:
        _camera_audio_hub = CameraAudioHub(_settings)
    return _camera_audio_hub


def get_camera_source_registry() -> CameraSourceRegistry:
    global _camera_source_registry
    if _camera_source_registry is None:
        _camera_source_registry = CameraSourceRegistry(_settings)
    return _camera_source_registry


def get_camera_setup_config_service() -> CameraSetupConfigService:
    global _camera_setup_config_service
    if _camera_setup_config_service is None:
        _camera_setup_config_service = CameraSetupConfigService(_settings, get_camera_source_registry())
    return _camera_setup_config_service


def get_camera_source_settings(camera_id: str):
    return get_camera_source_registry().settings_for(camera_id)


def get_camera_source_frame_hub(camera_id: str) -> CameraFrameHub:
    normalized = camera_id.strip().lower()
    hub = _camera_source_frame_hubs.get(normalized)
    if hub is None:
        hub = CameraFrameHub(get_camera_source_settings(camera_id))
        _camera_source_frame_hubs[normalized] = hub
    return hub


def get_camera_source_audio_hub(camera_id: str) -> CameraAudioHub:
    normalized = camera_id.strip().lower()
    hub = _camera_source_audio_hubs.get(normalized)
    if hub is None:
        hub = CameraAudioHub(get_camera_source_settings(camera_id))
        _camera_source_audio_hubs[normalized] = hub
    return hub


def get_camera_source_processed_frame_hub(camera_id: str) -> CombinedProcessedFrameHub:
    normalized = camera_id.strip().lower()
    hub = _camera_source_processed_hubs.get(normalized)
    if hub is None:
        hub = CombinedProcessedFrameHub(
            get_camera_source_settings(camera_id),
            pose_payload_provider=lambda: None,
            fall_payload_provider=lambda: None,
        )
        _camera_source_processed_hubs[normalized] = hub
    return hub


async def shutdown_camera_source_hubs() -> None:
    for hub in list(_camera_source_audio_hubs.values()):
        await hub.shutdown()
    _camera_source_audio_hubs.clear()
    _camera_source_processed_hubs.clear()
    _camera_source_frame_hubs.clear()


def get_effective_device_ingest_mode(
    device_mac: str,
    stored_mode: DeviceIngestMode | str | None,
) -> DeviceIngestMode | None:
    normalized_mac = device_mac.strip().upper()
    personas = getattr(_data_generator, "personas", None)
    if personas:
        known = {str(persona.mac_address).strip().upper() for persona in personas if getattr(persona, "mac_address", None)}
        if normalized_mac in known:
            return DeviceIngestMode.MOCK
    if stored_mode is None:
        return None
    if isinstance(stored_mode, DeviceIngestMode):
        return stored_mode
    try:
        return DeviceIngestMode(str(stored_mode))
    except ValueError:
        return None


def is_display_ready_sample(sample: HealthSample, ingest_mode: DeviceIngestMode | str | None) -> bool:
    effective = get_effective_device_ingest_mode(sample.device_mac, ingest_mode)
    if effective == DeviceIngestMode.MOCK:
        return True
    if effective == DeviceIngestMode.SERIAL:
        # 串口模式：收到即更新，缺失字段由 _merge_with_latest 回填上一时刻值。
        if sample.heart_rate <= 0 or sample.blood_oxygen <= 0:
            return False
        if sample.temperature <= 0:
            return False
        return True
    return True


def _filter_display_samples(
    samples: list[HealthSample],
    ingest_mode: DeviceIngestMode | str | None,
) -> list[HealthSample]:
    if not samples:
        return []
    effective_mode = get_effective_device_ingest_mode(samples[0].device_mac, ingest_mode)
    ordered = sorted(samples, key=lambda item: item.timestamp)
    if effective_mode != DeviceIngestMode.SERIAL:
        return ordered
    resolved: list[HealthSample] = []
    last_valid_spo2: int | None = None
    for sample in ordered:
        update: dict[str, object] = {}
        if sample.blood_oxygen in (None, 0) and last_valid_spo2 not in (None, 0):
            update["blood_oxygen"] = last_valid_spo2
        resolved_sample = sample.model_copy(update=update) if update else sample
        if resolved_sample.blood_oxygen not in (None, 0):
            last_valid_spo2 = resolved_sample.blood_oxygen
        resolved.append(resolved_sample)
    return resolved


def get_display_latest_sample(
    device_mac: str,
    ingest_mode: DeviceIngestMode | str | None,
) -> HealthSample | None:
    effective_mode = get_effective_device_ingest_mode(device_mac, ingest_mode)
    recent = _stream_service.recent(device_mac, limit=240)
    if not recent:
        now = datetime.now(timezone.utc)
        persisted = _health_data_repository.list_samples(
            device_mac=device_mac.strip().upper(),
            start_at=now - timedelta(hours=24),
            end_at=now,
            limit=240,
        )
        if persisted:
            restored = _filter_display_samples(persisted, effective_mode)
            for sample in restored:
                if is_display_ready_sample(sample, effective_mode):
                    _stream_service.publish(sample)
            recent = restored

    filtered = _filter_display_samples(recent, effective_mode)
    for sample in reversed(filtered):
        if is_display_ready_sample(sample, effective_mode):
            return sample
    return None


def get_display_trend_samples(
    device_mac: str,
    ingest_mode: DeviceIngestMode | str | None,
    *,
    minutes: int,
    limit: int,
) -> list[HealthSample]:
    effective_mode = get_effective_device_ingest_mode(device_mac, ingest_mode)
    requested_limit = max(1, int(limit))
    minutes = max(1, int(minutes))
    samples = _stream_service.recent_in_window(device_mac, minutes=minutes, limit=max(240, requested_limit * 3))
    if not samples:
        now = datetime.now(timezone.utc)
        persisted = _health_data_repository.list_samples(
            device_mac=device_mac.strip().upper(),
            start_at=now - timedelta(minutes=minutes),
            end_at=now,
            limit=max(240, requested_limit * 3),
        )
        restored = _filter_display_samples(persisted, effective_mode)
        for sample in restored:
            if is_display_ready_sample(sample, effective_mode):
                _stream_service.publish(sample)
        samples = restored

    filtered = _filter_display_samples(samples, effective_mode)
    ready = [sample for sample in filtered if is_display_ready_sample(sample, effective_mode)]
    return ready[-requested_limit:]


def _restore_recent_samples_to_stream(*, hours: int = 24, per_device_limit: int = 288) -> None:
    now = datetime.now(timezone.utc)
    devices = _device_service.list_devices()
    histories = _health_data_repository.list_samples_by_devices(
        device_macs=[device.mac_address for device in devices],
        start_at=now - timedelta(hours=hours),
        end_at=now,
        per_device_limit=per_device_limit,
    )
    for device in devices:
        effective_mode = get_effective_device_ingest_mode(device.mac_address, device.ingest_mode)
        samples = histories.get(device.mac_address, [])
        filtered = _filter_display_samples(samples, effective_mode)
        for sample in filtered:
            if is_display_ready_sample(sample, effective_mode):
                _stream_service.publish(sample)


def _normalize_mac_from_payload(payload: dict[str, object]) -> str:
    return str(payload.get("mac_address", "")).strip().upper()


def _tool_get_device_realtime(payload: dict[str, object]) -> dict[str, object]:
    mac = _normalize_mac_from_payload(payload)
    sample = _stream_service.latest(mac)
    device = _device_service.get_device(mac)
    return {
        "mac_address": mac,
        "timestamp": sample.timestamp.isoformat() if sample else None,
        "heart_rate": sample.heart_rate if sample else None,
        "blood_oxygen": sample.blood_oxygen if sample else None,
        "temperature": sample.temperature if sample else None,
        "blood_pressure": sample.blood_pressure if sample else None,
        "battery": sample.battery if sample else None,
        "steps": sample.steps if sample else None,
        "health_score": sample.health_score if sample else None,
        "sos_flag": sample.sos_flag if sample else None,
        "device_status": device.status if device else None,
    }


def _tool_get_device_trend(payload: dict[str, object]) -> dict[str, object]:
    mac = _normalize_mac_from_payload(payload)
    minutes = int(payload.get("minutes", 180) or 180)
    limit = int(payload.get("limit", 120) or 120)
    points = _stream_service.trend(mac, minutes=minutes, limit=limit)
    return {
        "mac_address": mac,
        "minutes": minutes,
        "points": [point.model_dump(mode="json") for point in points],
    }


def _tool_get_device_status(payload: dict[str, object]) -> dict[str, object]:
    mac = _normalize_mac_from_payload(payload)
    device = _device_service.get_device(mac)
    return {
        "mac_address": mac,
        "device_name": device.device_name if device else None,
        "status": device.status if device else None,
        "bind_status": device.bind_status if device else None,
        "user_id": device.user_id if device else None,
    }


def _tool_get_device_bind_history(payload: dict[str, object]) -> dict[str, object]:
    mac = _normalize_mac_from_payload(payload)
    logs = _device_service.list_bind_logs(mac)
    return {
        "mac_address": mac,
        "logs": [log.model_dump(mode="json") for log in logs],
    }


def _tool_get_elder_profile(payload: dict[str, object]) -> dict[str, object]:
    directory = _care_service.get_directory()
    elder_user_id = str(payload.get("elder_user_id", "")).strip()
    mac = _normalize_mac_from_payload(payload)
    elder = None
    if elder_user_id:
        elder = next((item for item in directory.elders if item.id == elder_user_id), None)
    elif mac:
        elder = next(
            (
                item
                for item in directory.elders
                if mac == item.device_mac or mac in getattr(item, "device_macs", [])
            ),
            None,
        )
    return {
        "elder_user_id": elder.id if elder else elder_user_id or None,
        "name": elder.name if elder else None,
        "age": elder.age if elder else None,
        "apartment": elder.apartment if elder else None,
        "community_id": elder.community_id if elder else None,
        "device_mac": elder.device_mac if elder else mac or None,
        "device_macs": list(getattr(elder, "device_macs", [])) if elder else ([mac] if mac else []),
        "family_ids": elder.family_ids if elder else [],
    }


def _tool_get_family_relations(payload: dict[str, object]) -> dict[str, object]:
    elder_user_id = str(payload.get("elder_user_id", "")).strip()
    family_user_id = str(payload.get("family_user_id", "")).strip()
    relations = []
    if elder_user_id:
        relations = _relation_service.list_relations_by_elder(elder_user_id)
    elif family_user_id:
        relations = _relation_service.list_relations_by_family(family_user_id)
    return {
        "relations": [relation.model_dump(mode="json") for relation in relations],
    }


def _tool_get_active_alarms(payload: dict[str, object]) -> dict[str, object]:
    mac = _normalize_mac_from_payload(payload)
    active_only = bool(payload.get("active_only", True))
    alarms = _alarm_service.list_alarms(device_mac=mac or None, active_only=active_only)
    return {
        "mac_address": mac or None,
        "alarms": [alarm.model_dump(mode="json") for alarm in alarms],
    }


def _tool_get_community_overview(payload: dict[str, object]) -> dict[str, object]:
    latest_samples = _stream_service.latest_samples()
    history_by_device = _stream_service.recent_by_devices(minutes=60, per_device_limit=60)
    summary = _community_clusterer.summarize(latest_samples, history_by_device)
    score = _intelligent_scorer.score_sequence(
        [
            [sample.heart_rate, sample.temperature, sample.blood_oxygen, (sample.blood_pressure_pair or (120, 80))[0]]
            for sample in latest_samples
        ]
    ) if latest_samples else 0.0
    return {
        "community_id": str(payload.get("community_id", "community-haitang") or "community-haitang"),
        "device_count": len(latest_samples),
        "intelligent_anomaly_score": score,
        "clusters": summary.clusters,
        "trend": summary.trend,
    }


def _tool_placeholder_external(tool_name: str, payload: dict[str, object]) -> dict[str, object]:
    return {
        "tool_name": tool_name,
        "status": "reserved",
        "message": "External provider not connected in current runtime",
        "requested_payload": payload,
    }


def _tool_holiday_lookup(payload: dict[str, object]) -> dict[str, object]:
    target = str(payload.get("date", "")).strip()
    try:
        day = datetime.fromisoformat(target).date() if target else datetime.now(timezone.utc).date()
    except ValueError:
        day = datetime.now(timezone.utc).date()
    is_weekend = day.weekday() >= 5
    return {
        "date": day.isoformat(),
        "is_holiday": is_weekend,
        "is_weekend": is_weekend,
        "label": "weekend" if is_weekend else "workday",
        "source_note": "local_placeholder_calendar",
    }


def _tool_generate_analysis_report(payload: dict[str, object]) -> dict[str, object]:
    scope = str(payload.get("scope", "community"))
    window = str(payload.get("window", "day"))
    if scope != "community":
        title = "老人健康分析报告"
        summary = "窗口内健康态势结构化报告"
        report_payload = {
            "scope": scope,
            "window": window,
            "sections": [
                {"title": "摘要", "content": "关键指标与事件汇总"},
                {"title": "风险评估", "content": "风险等级与触发原因"},
                {"title": "建议动作", "content": "建议的处置与观察措施"},
            ],
        }
        return {
            "report": report_payload,
            "attachments": [
                {
                    "id": f"analysis-report-{scope}-{window}",
                    "title": title,
                    "summary": summary,
                    "render_type": "report_document",
                    "render_payload": report_payload,
                    "source_tool": "generate_analysis_report",
                }
            ],
        }

    window_kind = WindowKind.WEEK if window == "week" else WindowKind.DAY
    device_macs = [str(item).strip().upper() for item in list(payload.get("device_macs", [])) if str(item).strip()]
    window_report = _community_insight_service.build_window_report(window=window_kind, device_macs=device_macs)
    analysis = window_report.analysis.model_dump(mode="json")
    key_metrics = analysis.get("key_metrics", {})
    risk_distribution = analysis.get("risk_distribution", {})
    alert_breakdown = analysis.get("alert_breakdown", {})
    status_distribution = analysis.get("device_status_distribution", {})
    high_risk_entities = analysis.get("high_risk_entities", [])
    trend_findings = analysis.get("trend_findings", [])
    chart_payloads = analysis.get("chart_payloads", [])

    title = f"社区{('过去一周' if window_kind == WindowKind.WEEK else '过去一天')}健康分析报告"

    metric_rows = [
        ("覆盖设备数", key_metrics.get("device_count", 0)),
        ("有效上报设备", key_metrics.get("reported_device_count", 0)),
        ("离线设备", key_metrics.get("offline_device_count", 0)),
        ("高风险对象", key_metrics.get("high_risk_device_count", 0)),
        ("窗口告警数", key_metrics.get("window_alert_count", 0)),
        ("平均健康分", key_metrics.get("average_health_score", "--")),
        ("平均血氧", key_metrics.get("average_blood_oxygen", "--")),
    ]
    metric_markdown = "\n".join(
        [
            "| 指标 | 数值 |",
            "| --- | --- |",
            *[f"| {label} | {value} |" for label, value in metric_rows],
        ]
    )

    risk_rows = [
        {
            "elder_name": str(item.get("elder_name") or "--"),
            "device_mac": str(item.get("device_mac") or "--"),
            "risk_level": str(item.get("risk_level") or "--"),
            "latest_health_score": item.get("latest_health_score") if item.get("latest_health_score") is not None else "--",
            "active_alert_count": int(item.get("active_alert_count", 0) or 0),
            "reasons": "；".join(str(reason) for reason in item.get("reasons", [])[:3]) or "--",
        }
        for item in high_risk_entities[:8]
        if isinstance(item, dict)
    ]
    risk_markdown = (
        "\n".join(
            [
                "| 老人 | 设备 | 风险 | 健康分 | 活跃告警 | 原因 |",
                "| --- | --- | --- | --- | --- | --- |",
                *[
                    f"| {row['elder_name']} | {row['device_mac']} | {row['risk_level']} | {row['latest_health_score']} | {row['active_alert_count']} | {row['reasons']} |"
                    for row in risk_rows
                ],
            ]
        )
        if risk_rows
        else "当前窗口内暂无可排序的高风险对象。"
    )

    alert_rows = [
        {"alarm_type": str(key), "count": int(value or 0)}
        for key, value in alert_breakdown.items()
    ]
    alert_rows.sort(key=lambda item: item["count"], reverse=True)
    alert_markdown = (
        "\n".join(
            [
                "| 告警类型 | 次数 |",
                "| --- | --- |",
                *[f"| {row['alarm_type']} | {row['count']} |" for row in alert_rows[:10]],
            ]
        )
        if alert_rows
        else "当前窗口内暂无告警热点。"
    )

    status_rows = [
        {"status": str(key), "count": int(value or 0)}
        for key, value in status_distribution.items()
    ]
    status_rows.sort(key=lambda item: item["count"], reverse=True)
    status_markdown = (
        "\n".join(
            [
                "| 设备状态 | 数量 |",
                "| --- | --- |",
                *[f"| {row['status']} | {row['count']} |" for row in status_rows[:10]],
            ]
        )
        if status_rows
        else "当前没有设备状态分布数据。"
    )

    advice: list[str] = []
    if risk_rows:
        focus_names = "、".join(row["elder_name"] for row in risk_rows[:3])
        advice.append(f"优先复核 {focus_names} 的最新生命体征和现场状态。")
    if int(key_metrics.get("offline_device_count", 0) or 0) > 0:
        advice.append("尽快排查离线设备链路、佩戴状态与电量，避免持续缺数。")
    if int(key_metrics.get("window_alert_count", 0) or 0) > 0:
        advice.append("结合告警热点安排分级随访，优先处理 SOS、血氧偏低与体温异常。")
    if float(key_metrics.get("average_health_score", 0) or 0) < 75:
        advice.append("建议在下一轮巡检中复测健康评分偏低对象的关键指标。")
    if not advice:
        advice.append("社区整体态势相对平稳，可维持常规巡检并持续观察异常漂移。")

    summary = (
        f"覆盖设备 {key_metrics.get('device_count', 0)} 台，"
        f"有效上报 {key_metrics.get('reported_device_count', 0)} 台，"
        f"高风险对象 {key_metrics.get('high_risk_device_count', 0)} 台，"
        f"窗口告警 {key_metrics.get('window_alert_count', 0)} 条。"
    )

    sections = [
        {"title": "执行摘要", "content": summary},
        {"title": "关键指标表", "content": metric_markdown},
        {"title": "高风险对象表", "content": risk_markdown},
        {"title": "告警热点表", "content": alert_markdown},
        {"title": "设备状态表", "content": status_markdown},
        {"title": "趋势发现", "content": "\n".join(f"- {item}" for item in trend_findings[:8]) or "暂无显著趋势发现。"},
        {"title": "处置建议", "content": "\n".join(f"- {item}" for item in advice[:6])},
    ]

    report_payload = {
        "scope": scope,
        "window": window,
        "document_title": title,
        "generated_at": window_report.generated_at.isoformat(),
        "sections": sections,
        "charts": chart_payloads,
    }

    attachments = [
        {
            "id": f"analysis-report-{scope}-{window}",
            "title": title,
            "summary": summary,
            "render_type": "report_document",
            "render_payload": report_payload,
            "source_tool": "generate_analysis_report",
        },
        {
            "id": f"analysis-report-metrics-{window}",
            "title": "社区关键指标",
            "summary": "窗口内核心监测指标概览",
            "render_type": "metric_cards",
            "render_payload": {
                "items": [
                    {"label": "覆盖设备数", "value": key_metrics.get("device_count", 0)},
                    {"label": "有效上报设备", "value": key_metrics.get("reported_device_count", 0)},
                    {"label": "离线设备", "value": key_metrics.get("offline_device_count", 0)},
                    {"label": "高风险对象", "value": key_metrics.get("high_risk_device_count", 0)},
                    {"label": "窗口告警数", "value": key_metrics.get("window_alert_count", 0)},
                    {"label": "平均健康分", "value": key_metrics.get("average_health_score", "--")},
                ]
            },
            "source_tool": "generate_analysis_report",
        },
    ]

    if risk_rows:
        attachments.append(
            {
                "id": f"analysis-report-risk-table-{window}",
                "title": "高风险对象明细",
                "summary": "按风险等级、健康分和活跃告警排序",
                "render_type": "table",
                "render_payload": {
                    "columns": [
                        {"key": "elder_name", "label": "老人"},
                        {"key": "device_mac", "label": "设备 MAC"},
                        {"key": "risk_level", "label": "风险等级"},
                        {"key": "latest_health_score", "label": "最新健康分"},
                        {"key": "active_alert_count", "label": "活跃告警"},
                        {"key": "reasons", "label": "主要原因"},
                    ],
                    "rows": risk_rows,
                },
                "source_tool": "generate_analysis_report",
            }
        )

    if alert_rows:
        attachments.append(
            {
                "id": f"analysis-report-alert-table-{window}",
                "title": "告警热点统计",
                "summary": "窗口内告警类型分布",
                "render_type": "table",
                "render_payload": {
                    "columns": [
                        {"key": "alarm_type", "label": "告警类型"},
                        {"key": "count", "label": "次数"},
                    ],
                    "rows": alert_rows[:10],
                },
                "source_tool": "generate_analysis_report",
            }
        )

    for index, chart in enumerate(chart_payloads[:6]):
        if not isinstance(chart, dict) or not isinstance(chart.get("echarts_option"), dict):
            continue
        attachments.append(
            {
                "id": str(chart.get("id") or f"analysis-report-chart-{index}"),
                "title": str(chart.get("title") or f"图表 {index + 1}"),
                "summary": str(chart.get("summary") or "报告附带图表"),
                "render_type": "echarts",
                "render_payload": {
                    "id": str(chart.get("id") or f"analysis-report-chart-{index}"),
                    "title": str(chart.get("title") or f"图表 {index + 1}"),
                    "summary": str(chart.get("summary") or ""),
                    "echarts_option": chart.get("echarts_option"),
                },
                "source_tool": "generate_analysis_report",
            }
        )

    return {
        "summary": summary,
        "report": report_payload,
        "attachments": attachments,
    }

def _care_directory_lookup(device_mac: str) -> dict[str, object]:
    directory = _care_service.get_directory()
    normalized = device_mac.upper()
    elder = next(
        (
            item
            for item in directory.elders
            if normalized == item.device_mac or normalized in getattr(item, "device_macs", [])
        ),
        None,
    )
    families = [
        family.model_dump(mode="json")
        for family in directory.families
        if elder and family.id in elder.family_ids
    ]
    return {
        "elder_profile": elder.model_dump(mode="json") if elder else None,
        "family_profiles": families,
    }


def _merge_with_latest(sample: HealthSample) -> HealthSample:
    latest = _stream_service.latest(sample.device_mac)
    if latest is None:
        return sample

    update: dict[str, object] = {}

    # 收到什么就更新什么；没带到的字段沿用上一时刻值。
    if sample.heart_rate <= 0 and latest.heart_rate > 0:
        update["heart_rate"] = latest.heart_rate
    if sample.blood_oxygen <= 0 and latest.blood_oxygen > 0:
        update["blood_oxygen"] = latest.blood_oxygen
    if sample.temperature <= 0 and 35.0 <= latest.temperature <= 45.0:
        update["temperature"] = latest.temperature

    if (not sample.blood_pressure or sample.blood_pressure == "0/0") and latest.blood_pressure:
        update["blood_pressure"] = latest.blood_pressure
    if sample.battery <= 0 and latest.battery > 0:
        update["battery"] = latest.battery
    if (sample.steps is None or sample.steps <= 0) and (latest.steps is not None and latest.steps > 0):
        update["steps"] = latest.steps
    if sample.ambient_temperature is None and latest.ambient_temperature is not None:
        update["ambient_temperature"] = latest.ambient_temperature
    if sample.surface_temperature is None and latest.surface_temperature is not None:
        update["surface_temperature"] = latest.surface_temperature
    if not sample.device_uuid and latest.device_uuid:
        update["device_uuid"] = latest.device_uuid

    return sample.model_copy(update=update) if update else sample


def _persist_structured_health_score(sample: HealthSample, device: DeviceRecord) -> None:
    """Persist ML/rule split scores so dashboard can render rule/model breakdown."""
    systolic, diastolic = sample.blood_pressure_pair
    vitals = VitalSignsPayload(
        heart_rate=float(sample.heart_rate),
        spo2=float(sample.blood_oxygen),
        sbp=float(systolic),
        dbp=float(diastolic),
        body_temp=float(sample.temperature),
        fall_detection=False,
        data_accuracy=100.0,
    )
    elderly_id = str(device.user_id or f"UNBOUND:{sample.device_mac}")
    try:
        _structured_health_score_service.evaluate_vitals(
            vitals=vitals,
            elderly_id=elderly_id,
            device_id=sample.device_mac,
            timestamp=sample.timestamp,
            persist=True,
            stateful_stability=True,
        )
    except Exception as exc:
        logger.warning(
            "Structured score persistence failed for %s: %s",
            sample.device_mac,
            exc,
        )
        fallback_score = float(sample.health_score or 0)
        if fallback_score >= 85:
            fallback_risk_level = "normal"
        elif fallback_score >= 70:
            fallback_risk_level = "attention"
        elif fallback_score >= 55:
            fallback_risk_level = "warning"
        else:
            fallback_risk_level = "critical"

        fallback_tags: list[str] = []
        fallback_reasons: list[str] = []
        if sample.sos_flag:
            fallback_tags.append("sos")
            fallback_reasons.append("Detected SOS signal from device")
        if sample.blood_oxygen < 93:
            fallback_tags.append("spo2_low")
            fallback_reasons.append(f"SpO2 is low ({sample.blood_oxygen}%)")
        if sample.heart_rate > 120 or sample.heart_rate < 50:
            fallback_tags.append("heart_rate_abnormal")
            fallback_reasons.append(f"Heart rate out of preferred range ({sample.heart_rate} bpm)")
        if sample.temperature >= 37.6:
            fallback_tags.append("temperature_high")
            fallback_reasons.append(f"Body temperature elevated ({sample.temperature:.1f} C)")

        fallback_payload = {
            "elderly_id": elderly_id,
            "device_id": sample.device_mac,
            "timestamp": sample.timestamp.isoformat(),
            "health_score": round(fallback_score, 4),
            "final_health_score": round(fallback_score, 4),
            "rule_health_score": round(fallback_score, 4),
            "model_health_score": round(fallback_score, 4),
            "risk_level": fallback_risk_level,
            "risk_score_raw": round(max(0.0, min(1.0, 1.0 - (fallback_score / 100.0))), 6),
            "sub_scores": {
                "rule_health_score": round(fallback_score, 4),
                "model_health_score": round(fallback_score, 4),
                "final_health_score": round(fallback_score, 4),
            },
            "alerts": {
                "hr_alert": {"label": "High" if sample.heart_rate > 120 else ("Low" if sample.heart_rate < 50 else "Normal"), "probability": None},
                "spo2_alert": {"label": "Low" if sample.blood_oxygen < 93 else "Normal", "probability": None},
                "bp_alert": {"label": "Normal", "probability": None},
                "temp_alert": {"label": "Abnormal" if sample.temperature >= 37.6 else "Normal", "probability": None},
                "hard_threshold_level": fallback_risk_level if fallback_risk_level in {"warning", "critical"} else None,
            },
            "abnormal_tags": fallback_tags,
            "trigger_reasons": fallback_reasons,
            "recommendation_code": "EMERGENCY_CONTACT" if sample.sos_flag else "MONITOR",
            "stability_mode": "rule_fallback",
            "stabilized_vitals": {
                "heart_rate": float(sample.heart_rate),
                "spo2": float(sample.blood_oxygen),
                "sbp": float(systolic),
                "dbp": float(diastolic),
                "body_temp": float(sample.temperature),
                "fall_detection": False,
                "data_accuracy": 100.0,
            },
            "active_events": [],
            "score_adjustment_reason": "Structured model artifacts missing; fallback scores are used.",
        }
        try:
            _score_repo.save_result(
                elderly_id=elderly_id,
                device_id=sample.device_mac,
                timestamp=sample.timestamp,
                result=fallback_payload,
            )
        except Exception as fallback_exc:
            logger.warning(
                "Structured fallback persistence failed for %s: %s",
                sample.device_mac,
                fallback_exc,
            )


async def ingest_sample(sample: HealthSample) -> IngestResponse:
    global _last_community_alarm_at

    if _settings.data_mode == "mock" and _settings.use_mock_data:
        device = _device_service.ensure_device(sample.device_mac, device_name=_settings.default_device_name)
    else:
        device = _device_service.get_device(sample.device_mac)
    if not isinstance(device, DeviceRecord):
        raise RuntimeError("Device must be registered before ingest in formal mode")

    _device_service.update_status(sample.device_mac, DeviceStatus.ONLINE)

    _alarm_service.observe_sample(sample)

    # 【性能优化】第一时间评估并提取实时告警（包括SOS）。直接评估未 merged 的 sample_0。
    realtime_alarms = _alarm_service.evaluate(sample)
    
    # 若有紧急告警，第一时间 WebSocket 广播，避免被后续同步数据库写操作阻塞而导致高延迟
    if realtime_alarms:
        _health_data_repository.persist_alerts(realtime_alarms)
        for alarm in realtime_alarms:
            await _websocket_manager.broadcast_alarm(alarm.model_dump(mode="json"))
        await _websocket_manager.broadcast_alarm_queue(
            {
                "type": "alarm_queue",
                "queue": [item.model_dump(mode="json") for item in _alarm_service.queue_items(active_only=True)],
                "snapshot": _alarm_service.queue_snapshot(),
            }
        )

    # 之后合并历史以填补异常的0或缺失数据，保证展示与入库的质量
    sample = _merge_with_latest(sample)

    baseline = _baseline_tracker.observe(sample)
    sample.health_score = _health_score_service.score(sample, baseline)
    _health_data_repository.persist_sample(sample)
    _health_data_repository.refresh_rollups_for_sample(
        device_mac=sample.device_mac,
        timestamp=sample.timestamp,
    )
    _stream_service.publish(sample)
    _persist_structured_health_score(sample, device)

    ml_alarms = []
    intelligent_result = _intelligent_scorer.infer_device(
        sample.device_mac,
        _stream_service.recent_in_window(sample.device_mac, minutes=60, limit=360),
        now=sample.timestamp,
    )
    if intelligent_result:
        intelligent_alarm = _intelligent_scorer.build_alarm(sample, intelligent_result)
        if intelligent_alarm:
            ml_alarms.extend(_alarm_service.evaluate_alarm_records([intelligent_alarm]))

    now = sample.timestamp.astimezone(timezone.utc)
    if _last_community_alarm_at is None or now - _last_community_alarm_at >= timedelta(hours=1):
        community_summary = _community_clusterer.summarize(
            _stream_service.latest_samples(),
            _stream_service.recent_by_devices(minutes=60, per_device_limit=60),
        )
        community_alarm = _community_clusterer.build_alarm(community_summary)
        if community_alarm:
            ml_alarms.extend(_alarm_service.evaluate_alarm_records([community_alarm]))
            _last_community_alarm_at = now

    if ml_alarms:
        _health_data_repository.persist_alerts(ml_alarms)
        for alarm in ml_alarms:
            await _websocket_manager.broadcast_alarm(alarm.model_dump(mode="json"))
        await _websocket_manager.broadcast_alarm_queue(
            {
                "type": "alarm_queue",
                "queue": [item.model_dump(mode="json") for item in _alarm_service.queue_items(active_only=True)],
                "snapshot": _alarm_service.queue_snapshot(),
            }
        )

    await _websocket_manager.broadcast_health(sample.device_mac, sample.model_dump(mode="json"))

    all_alarms = (realtime_alarms or []) + (ml_alarms or [])
    return IngestResponse(success=True, message="Sample ingested", device_mac=sample.device_mac)


async def _ingest_video_bridge_alarm_event(event: dict[str, object]) -> AlarmRecord | None:
    metadata = dict(event.get("metadata") or {}) if isinstance(event.get("metadata"), dict) else {}
    configured_device_id = str(
        metadata.get("target_device_mac")
        or event.get("device_mac")
        or _settings.resolved_fall_detection_target_device_mac
    ).strip().upper()
    if not configured_device_id:
        configured_device_id = "CAMERA-VIDEO-BRIDGE"

    device_identity = configured_device_id
    pseudo_mac = _video_bridge_pseudo_mac(device_identity)

    _device_service.ensure_device(
        pseudo_mac,
        device_name="VIDEO-BRIDGE-CAMERA",
        ingest_mode=DeviceIngestMode.MOCK,
    )
    _device_service.update_status(pseudo_mac, DeviceStatus.ONLINE)

    state = str(event.get("state") or event.get("status") or "confirmed_fall").strip()
    camera_id = str(event.get("camera_id") or "").strip()
    risk = str(event.get("risk") or event.get("risk_level") or "high").strip()
    fall_score_raw = event.get("fall_score") or event.get("fall_prob")
    try:
        fall_score = float(fall_score_raw) if fall_score_raw is not None else None
    except (TypeError, ValueError):
        fall_score = None

    if fall_score is not None and fall_score >= 0.82:
        level = AlarmPriority.CRITICAL
    elif risk in {"critical", "high"}:
        level = AlarmPriority.CRITICAL
    else:
        level = AlarmPriority.WARNING

    message_parts = ["视频跌倒告警"]
    if camera_id:
        message_parts.append(f"camera={camera_id}")
    if state:
        message_parts.append(f"state={state}")
    if fall_score is not None:
        message_parts.append(f"score={fall_score:.2f}")
    message = " | ".join(message_parts)

    enriched_metadata = {
        **metadata,
        "source": event.get("source") or "vision_service",
        "trigger": metadata.get("trigger") or "video_bridge_fall_events",
        "target_device_mac": device_identity,
        "target_device_pseudo_mac": pseudo_mac,
        "camera_id": camera_id,
        "stream_name": event.get("stream_name"),
        "incident_id": event.get("incident_id"),
        "track_id": event.get("track_id"),
        "snapshot_url": event.get("snapshot_url") or event.get("snapshot_path"),
        "risk": risk,
        "state": state,
        "event_type": event.get("event_type") or "fall_confirmed",
        "fall_score": fall_score,
        "raw_event": event,
        "is_real_device": True,
    }

    alarm = AlarmRecord(
        device_mac=pseudo_mac,
        alarm_type=AlarmType.VIDEO_FALL,
        alarm_level=level,
        alarm_layer=AlarmLayer.INTELLIGENT,
        message=message,
        anomaly_probability=fall_score,
        metadata=enriched_metadata,
    )

    emitted = _alarm_service.evaluate_alarm_records([alarm])
    if not emitted:
        return None

    _health_data_repository.persist_alerts(emitted)
    for created_alarm in emitted:
        await _websocket_manager.broadcast_alarm(created_alarm.model_dump(mode="json"))
    await _websocket_manager.broadcast_alarm_queue(
        {
            "type": "alarm_queue",
            "queue": [item.model_dump(mode="json") for item in _alarm_service.queue_items(active_only=True)],
            "snapshot": _alarm_service.queue_snapshot(),
        }
    )
    return emitted[0]


def _video_bridge_pseudo_mac(device_identity: str) -> str:
    compact = "".join(ch for ch in str(device_identity or "").upper() if ch.isalnum())
    if len(compact) == 12 and all(ch in "0123456789ABCDEF" for ch in compact):
        return ":".join(compact[index : index + 2] for index in range(0, 12, 2))

    digest = str(abs(hash(device_identity or "VIDEO-BRIDGE")) % 10**10).rjust(10, "0")
    compact = f"AA{digest[:10]}".upper()
    return ":".join(compact[index : index + 2] for index in range(0, 12, 2))
