from __future__ import annotations

from functools import lru_cache
import json
from pathlib import Path
import sys
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from backend.runtime_bootstrap import resolve_runtime_bootstrap


BASE_DIR = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    """Application settings aligned with the 2026 competition platform."""

    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "AIoT Elder Care Monitoring System"
    environment: str = "development"
    api_v1_prefix: str = "/api/v1"
    debug: bool = True

    host: str = "0.0.0.0"
    port: int = 8000

    allowed_mac_prefixes: list[str] = Field(default_factory=list)
    mock_device_mac_prefix: str = "53:57:08"
    default_device_name: str = "T10-WATCH"
    device_uuid: str = "52616469-6F6C-616E-642D-541000000000"
    service_uuid: str = "00001803-494c-4f47-4943-544543480000"

    database_url: str = f"sqlite+aiosqlite:///{(BASE_DIR / 'data' / 'app.db').as_posix()}"
    redis_url: str = "redis://localhost:6379/0"
    chroma_path: str = str(BASE_DIR / "data" / "chroma")

    offline_only_runtime: bool = True
    llm_provider: Literal["auto", "qwen", "ollama"] = "qwen"
    local_model_routing: Literal["single", "task_router"] = "task_router"
    local_report_routing: Literal["fixed", "role_router"] = "fixed"
    local_approved_models: Annotated[
        list[str],
        NoDecode,
    ] = Field(default_factory=lambda: ["qwen3:1.7b", "deepseek-r1:1.5b"])
    local_default_model: str = "qwen3:1.7b"
    local_reasoning_model: str = "deepseek-r1:1.5b"
    local_report_model: str = "deepseek-r1:1.5b"

    qwen_api_base: str = ""
    qwen_api_key: str = ""
    dashscope_api_key_env: str = Field(default="", validation_alias="DASHSCOPE_API_KEY")
    qwen_model: str = ""
    qwen_embedding_model: str = ""
    qwen_rerank_model: str = ""
    qwen_asr_model: str = ""
    qwen_tts_model: str = ""
    qwen_omni_model: str = ""
    qwen_tts_voice: str = ""
    qwen_rerank_api: str = ""
    qwen_enable_rerank: bool = False
    tavily_api_key: str = ""

    weather_provider: Literal["mock", "qweather"] = "mock"
    qweather_api_key: str = ""
    qweather_api_host: str = ""
    qweather_location: str = ""
    qweather_timeout_seconds: float = Field(default=3.0, ge=0.5, le=10.0)

    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen3:1.7b"

    llm_timeout_seconds: int = 10
    dialogue_max_predict_tokens: int = 320
    dialogue_max_output_chars: int = 900
    rag_timeout_seconds: int = 15
    rag_top_k: int = 3
    rag_fetch_k: int = 8
    rag_chunk_size: int = 700
    rag_chunk_overlap: int = 150

    network_probe_url: str = ""
    network_probe_timeout_seconds: int = 3
    network_probe_cache_seconds: int = 20

    jwt_secret: str = "replace-me-in-production"
    seed_default_accounts: bool = True
    seed_default_password: str = "123456"
    ws_heartbeat_seconds: int = 30

    realtime_window_size: int = 30
    zscore_threshold: float = 2.4
    mock_device_count: int = 10
    mock_push_interval_seconds: float = 1.0
    use_mock_data: bool = True
    enable_mock_overlay: bool = False
    strict_source_match: bool = True
    data_mode: Literal["mock", "serial", "mqtt"] = "mock"
    shouhuan_script_path: str = str(BASE_DIR / "shouhuan.py")
    bootstrap_source: str = "fallback_mock"
    bootstrap_status: str = "fallback"
    bootstrap_reason: str = "shouhuan_missing"
    serial_enabled: bool = False
    serial_port: str = ""
    serial_baudrate: int = 115200
    serial_collection_strategy: Literal["single_target", "static_filter"] = "single_target"
    serial_packet_type: int = 5
    serial_packet_merge_timeout_seconds: float = 5.0
    serial_mac_filter: str = "53:57:08:00:00:00"
    serial_detection_keywords: list[str] = Field(
        default_factory=lambda: [
            "cp210",
            "usb serial",
            "nrf",
            "silicon labs",
            "ch9102",
            "wch",
            "usb-enhanced-serial",
        ]
    )
    serial_fallback_device_mac: str = ""
    serial_auto_configure: bool = True
    serial_disable_uuid_output: bool = True
    serial_apply_mac_filter: bool = False
    serial_apply_packet_type: bool = False
    serial_enable_broadcast_sos_overlay: bool = True
    serial_response_cycle_seconds: float = 0.4
    serial_broadcast_cycle_seconds: float = 0.1
    serial_command_delay_seconds: float = 0.12
    serial_dual_collector_enabled: bool = False
    serial_broadcast_port: str = ""
    serial_response_port: str = ""

    mqtt_enabled: bool = False
    mqtt_broker_host: str = "localhost"
    mqtt_broker_port: int = 1883
    mqtt_topic: str = "t10-gateway"
    mqtt_username: str = ""
    mqtt_password: str = ""
    mqtt_keepalive_seconds: int = 60

    sos_broadcast_window_seconds: int = 15
    health_score_floor: int = 35
    stream_retention_points: int = 600
    raw_data_dir: str = str(BASE_DIR / "data" / "raw")
    processed_data_dir: str = str(BASE_DIR / "data" / "processed")
    artifact_data_dir: str = str(BASE_DIR / "data" / "artifacts")
    camera_ip: str = ""
    camera_user: str = "admin"
    camera_password: str = ""
    camera_source_mode: Literal["auto", "rtsp", "local"] = "auto"
    camera_local_index: int = 0
    camera_runtime_base_url: str = ""
    camera_local_http_url: str = ""
    camera_local_backend: Literal["auto", "dshow", "msmf", "any"] = "dshow"
    camera_rtsp_path: str = "/tcp/av0_0"
    camera_rtsp_port: int = 10554
    camera_onvif_port: int = 10080
    camera_stream_rtsp_path: str = "/tcp/av0_1"
    camera_audio_rtsp_path: str = "/tcp/av0_1"
    camera_audio_sample_rate: int = 16000
    camera_audio_gateway_url: str = ""
    camera_sdk_dll_dir: str = ""
    camera_activex_clsid: str = ""
    camera_probe_timeout_seconds: float = 3.0
    camera_snapshot_timeout_seconds: float = 8.0
    camera_stream_fps: float = 24.0
    camera_stream_profile: Literal["smooth", "balanced", "quality"] = "balanced"
    camera_stream_quality_path: str = "/tcp/av0_0"
    camera_stream_smooth_path: str = "/tcp/av0_1"
    camera_stream_jpeg_quality: int = 4
    camera_stream_width: int = 0
    camera_stream_send_timeout_seconds: float = 0.35
    camera_stream_keep_warm: bool = False
    target_user_vision_warmup_enabled: bool = False
    vision_service_base_url: str = "http://127.0.0.1:8090"
    vision_service_local_base_url: str = "http://127.0.0.1:8090"
    vision_service_camera_id: str = "camera_01"
    vision_service_poll_enabled: bool = False
    vision_service_poll_hz: float = 2.0
    vision_service_timeout_seconds: float = 2.5
    vision_service_push_token: str = ""
    robot_gateway_enabled: bool = True
    robot_gateway_base_url: str = "http://127.0.0.1:8090"
    robot_gateway_timeout_seconds: float = 1.5
    robot_simulation_enabled: bool = False
    camera_ptz_move_seconds: float = 0.35
    camera_ptz_speed: float = 0.45
    camera1_name: str = "camera1"
    camera1_ip: str = ""
    camera1_user: str = ""
    camera1_password: str = ""
    camera1_rtsp_port: int = 0
    camera1_onvif_port: int = 0
    camera1_rtsp_path: str = ""
    camera1_stream_rtsp_path: str = ""
    camera1_audio_rtsp_path: str = ""
    camera2_name: str = "camera2"
    camera2_ip: str = ""
    camera2_user: str = ""
    camera2_password: str = ""
    camera2_rtsp_port: int = 0
    camera2_onvif_port: int = 0
    camera2_rtsp_path: str = ""
    camera2_stream_rtsp_path: str = ""
    camera2_audio_rtsp_path: str = ""
    static_health_data_path: str = str(BASE_DIR / "data" / "raw" / "patients_data_with_alerts.xlsx")
    static_health_sheet_name: str = ""
    static_model_dir: str = str(BASE_DIR / "data" / "artifacts" / "static_health")
    static_model_path: str = str(BASE_DIR / "data" / "artifacts" / "static_health" / "static_health_model.pt")
    static_scaler_path: str = str(BASE_DIR / "data" / "artifacts" / "static_health" / "feature_scaler.joblib")
    static_feature_columns_path: str = str(BASE_DIR / "data" / "artifacts" / "static_health" / "feature_columns.json")
    static_label_mapping_path: str = str(BASE_DIR / "data" / "artifacts" / "static_health" / "label_mapping.json")
    static_training_config_path: str = str(BASE_DIR / "data" / "artifacts" / "static_health" / "training_config.json")
    static_metrics_path: str = str(BASE_DIR / "data" / "artifacts" / "static_health" / "metrics.json")
    train_batch_size: int = 16
    train_epochs: int = 40
    train_learning_rate: float = 1e-3
    train_val_ratio: float = 0.2
    train_random_seed: int = 42
    allow_rule_only_fallback: bool = False
    alert_probability_threshold: float = 0.5
    model_fusion_rule_weight: float = 0.6
    model_fusion_model_weight: float = 0.4
    model_device: Literal["auto", "cpu", "cuda"] = "auto"
    fall_detection_enabled: bool = False
    fall_detection_model_root: str = str(BASE_DIR / "fall_detection_model_bundle")
    fall_detection_model_registry_path: str = ""
    fall_detection_python: str = sys.executable
    fall_detection_event_log: str = str(BASE_DIR / "data" / "fall_events" / "camera_events.jsonl")
    fall_detection_snapshot_dir: str = str(BASE_DIR / "data" / "fall_events" / "snapshots")
    fall_detection_profile: str = "private_scene_fusion_v2"
    fall_detection_speed_profile: Literal["accuracy", "balanced", "fast"] = "accuracy"
    fall_detection_threshold_override: float = 0.0
    fall_detection_process_every_override: int = 0
    fall_detection_alert_rules_path: str = ""
    fall_detection_injury_rules_path: str = ""
    fall_detection_target_device_mac: str = "CAMERA-192.168.8.254"
    fall_detection_target_elder_id: str = ""
    fall_detection_target_family_ids: str = ""
    fall_detection_status_log_interval_seconds: float = 2.0
    fall_detection_restart_delay_seconds: float = 5.0
    fall_detection_roi_enabled: bool = False
    fall_detection_roi_rect: str = ""
    fall_detection_roi_min_overlap: float = 0.5
    fall_detection_confirmed_roi_bypass_score: float = 0.6
    fall_detection_frame_width: float = 2304.0
    fall_detection_frame_height: float = 1296.0
    fall_detection_min_alert_score: float = 0.0
    fall_detection_confirmation_window_seconds: float = 8.0
    fall_detection_min_confirmed_hits: int = 2
    fall_detection_min_track_age_seconds: float = 0.8
    fall_detection_high_confidence_score: float = 0.72
    fall_detection_min_down_seconds: float = 1.2
    fall_detection_min_bbox_area_ratio: float = 0.008
    fall_detection_edge_margin_ratio: float = 0.015
    fall_detection_edge_partial_min_height_ratio: float = 0.22
    fall_detection_track_state_ttl_seconds: float = 120.0
    fall_detection_incident_reopen_seconds: float = 10.0
    fall_detection_multimodal_enabled: bool = True
    fall_detection_multimodal_provider: Literal["auto", "qwen_omni", "siliconflow_script", "disabled"] = "auto"
    fall_detection_multimodal_min_score: float = 0.45
    fall_detection_multimodal_timeout_seconds: int = 45
    pose_detection_enabled: bool = False
    pose_detection_model_root: str = str(BASE_DIR / "pose_detection_model_bundle")
    pose_detection_python: str = sys.executable
    pose_detection_event_log: str = str(BASE_DIR / "data" / "pose_events" / "pose_events.jsonl")
    pose_detection_latest_json: str = str(BASE_DIR / "data" / "pose_events" / "latest_pose.json")
    pose_detection_snapshot_dir: str = str(BASE_DIR / "data" / "pose_events" / "snapshots")
    pose_detection_profile: str = "default"
    pose_detection_process_every_override: int = 0
    pose_detection_status_log_interval_seconds: float = 1.5
    pose_detection_restart_delay_seconds: float = 5.0
    pose_detection_pose_conf_threshold: float = 0.25
    pose_detection_track_max_det: int = 8
    pose_detection_analysis_width: int = 960
    pose_detection_min_pose_score: float = 0.20
    pose_detection_bed_roi_rect: str = ""
    pose_detection_floor_roi_rect: str = ""
    pose_detection_single_frame_model_path: str = ""
    pose_detection_single_frame_imgsz: int = 320
    rule_quality_floor: float = 0.80
    poor_signal_quality_threshold: float = 85.0
    stability_profile: str = "robust_demo"
    stabilization_window_seconds: int = 45
    stabilization_max_points: int = 5
    stabilization_bp_points: int = 3
    stabilization_min_points: int = 3
    stabilization_history_cap: int = 120
    stability_recovery_points: int = 3
    stability_activation_min_abnormal_points: int = 2
    stability_default_sample_interval_seconds: int = 10
    stability_warning_aggregation_seconds: int = 60
    stability_explanation_refresh_seconds: int = 45
    score_max_drop_per_sample: float = 6.0
    stability_event_thresholds: dict[str, dict[str, float]] = Field(
        default_factory=lambda: {
            "tachycardia": {"enter": 105.0, "exit": 98.0},
            "bradycardia": {"enter": 50.0, "exit": 60.0},
            "low_spo2": {"enter": 89.0, "exit": 91.0},
            "hypertension": {"sbp_enter": 145.0, "dbp_enter": 92.0, "sbp_exit": 138.0, "dbp_exit": 88.0},
            "fever": {"enter": 37.5, "exit": 37.2},
            "poor_signal_quality": {"enter": 85.0, "exit": 88.0},
        }
    )
    stability_event_min_duration_seconds: dict[str, int] = Field(
        default_factory=lambda: {
            "tachycardia": 25,
            "bradycardia": 25,
            "low_spo2": 25,
            "hypertension": 45,
            "fever": 45,
            "poor_signal_quality": 20,
        }
    )
    rule_score_weights: dict[str, float] = Field(
        default_factory=lambda: {
            "heart_rate": 0.30,
            "spo2": 0.30,
            "blood_pressure": 0.25,
            "body_temp": 0.15,
        }
    )

    @field_validator("debug", mode="before")
    @classmethod
    def normalize_debug_flag(cls, value: object) -> object:
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"release", "prod", "production", "off", "false", "0", "no"}:
                return False
            if normalized in {"debug", "dev", "development", "on", "true", "1", "yes"}:
                return True
        return value

    @field_validator("local_approved_models", mode="before")
    @classmethod
    def normalize_local_approved_models(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip().lower() for item in value.split(",") if item.strip()]
        if isinstance(value, (list, tuple, set)):
            return [str(item).strip().lower() for item in value if str(item).strip()]
        return value

    @field_validator("local_default_model", "local_reasoning_model", "local_report_model", "ollama_model", mode="before")
    @classmethod
    def normalize_model_name(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().lower()
        return value

    @model_validator(mode="after")
    def validate_local_model_policy(self) -> "Settings":
        approved = set(self.supported_local_models)
        for model_name in (self.local_default_model, self.local_reasoning_model, self.local_report_model, self.ollama_model):
            if model_name not in approved:
                raise ValueError(
                    f"Unsupported local model '{model_name}'. Approved models: {', '.join(sorted(approved))}"
                )
        return self

    @model_validator(mode="after")
    def apply_runtime_bootstrap(self) -> "Settings":
        if self.data_mode == "mqtt" and self.mqtt_enabled:
            self.bootstrap_source = "mqtt_config"
            self.bootstrap_status = "ready"
            self.bootstrap_reason = "mqtt_runtime_selected"
            self.use_mock_data = False
            self.enable_mock_overlay = False
            self.serial_enabled = False
            return self

        bootstrap = resolve_runtime_bootstrap(self.shouhuan_script_path)
        self.bootstrap_source = bootstrap.bootstrap_source
        self.bootstrap_status = bootstrap.bootstrap_status
        self.bootstrap_reason = bootstrap.bootstrap_reason

        if bootstrap.port:
            self.serial_port = bootstrap.port
        if bootstrap.baudrate:
            self.serial_baudrate = bootstrap.baudrate
        if bootstrap.mac_address:
            self.serial_mac_filter = bootstrap.mac_address
        if bootstrap.packet_type:
            self.serial_packet_type = bootstrap.packet_type

        if bootstrap.mode == "serial":
            self.data_mode = "serial"
            self.serial_enabled = True
            self.use_mock_data = False
            self.enable_mock_overlay = True
            self.serial_collection_strategy = "single_target"
            self.serial_apply_mac_filter = False
            self.serial_apply_packet_type = False
            return self

        self.data_mode = "mock"
        self.serial_enabled = False
        self.use_mock_data = True
        self.enable_mock_overlay = False
        return self

    @model_validator(mode="after")
    def apply_shared_vision_runtime_override(self) -> "Settings":
        # `video_bridge_runtime_config.json` persists the shared Vision runtime override.
        # `/api/v1/vision/*` and `/api/v1/video-bridge/runtime-config` must resolve the
        # same effective upstream instead of acting like separate authorities.
        runtime_config_path = self.data_dir / "video_bridge_runtime_config.json"
        if not runtime_config_path.exists():
            return self
        try:
            payload = json.loads(runtime_config_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return self
        if not isinstance(payload, dict):
            return self

        base_url = str(payload.get("base_url") or "").strip().rstrip("/")
        if base_url:
            self.vision_service_base_url = base_url
        camera_id = str(payload.get("camera_id") or "").strip()
        if camera_id:
            self.vision_service_camera_id = camera_id
        if "poll_enabled" in payload:
            self.vision_service_poll_enabled = bool(payload.get("poll_enabled"))
        if "poll_hz" in payload:
            try:
                self.vision_service_poll_hz = max(0.2, min(5.0, float(payload.get("poll_hz") or 2.0)))
            except (TypeError, ValueError):
                pass
        if "timeout_seconds" in payload:
            try:
                self.vision_service_timeout_seconds = max(0.5, min(30.0, float(payload.get("timeout_seconds") or 2.5)))
            except (TypeError, ValueError):
                pass
        push_token = str(payload.get("push_token") or "").strip()
        if push_token:
            self.vision_service_push_token = push_token
        return self

    @property
    def data_dir(self) -> Path:
        return BASE_DIR / "data"

    @property
    def supported_local_models(self) -> tuple[str, ...]:
        approved = tuple(dict.fromkeys(model for model in self.local_approved_models if model))
        if approved:
            return approved
        return ("qwen3:1.7b", "deepseek-r1:1.5b")

    def _normalize_qwen_model(self, model: str) -> str:
        normalized = (model or "").strip()
        if not normalized:
            return "qwen3.5-flash"
        lower = normalized.lower()
        # 兼容脚本中指定的旧模型名和易出错名称，强制改为官方推荐模型
        if lower in {"qwen3.5-flash", "qwen3.5", "qwen3.5-flash-mini", "qwen3.5-lite"}:
            return "qwen3.5-flash"
        return normalized

    @property
    def qwen_llm_configured(self) -> bool:
        return bool(self.dashscope_api_key.strip() and (self._normalize_qwen_model(self.qwen_model) or self.qwen_omni_model.strip()))

    @property
    def qweather_configured(self) -> bool:
        return bool(
            self.weather_provider == "qweather"
            and self.qweather_api_key.strip()
            and self.qweather_api_host.strip()
            and self.qweather_location.strip()
        )

    @property
    def qwen_missing_config_fields(self) -> list[str]:
        missing: list[str] = []
        if not self.dashscope_api_key:
            missing.append("QWEN_API_KEY/DASHSCOPE_API_KEY")
        if not self.qwen_model.strip():
            missing.append("QWEN_MODEL")
        return missing

    @property
    def dashscope_api_key(self) -> str:
        return self.dashscope_api_key_env.strip() or self.qwen_api_key.strip()

    @property
    def tongyi_chat_model(self) -> str:
        return self._normalize_qwen_model(self.qwen_model)

    @property
    def tongyi_embedding_model(self) -> str:
        return self.qwen_embedding_model.strip() or "text-embedding-v2"

    @property
    def tongyi_rerank_model(self) -> str:
        return self.qwen_rerank_model.strip() or "gte-rerank-v2"

    @property
    def qwen_asr_model_name(self) -> str:
        return self.qwen_asr_model.strip() or "qwen3-asr-flash-realtime-2026-02-10"

    @property
    def qwen_asr_model_id(self) -> str:
        raw = self.qwen_asr_model.strip()
        if not raw:
            return "qwen3-asr-flash-realtime-2026-02-10"
        v = raw.lower()
        if v in {"qwen3-asr-flash", "qwen3-asr", "qwen-asr", "qwen3-asr-flash-realtime", "qwen-omni"}:
            return "qwen3-asr-flash-realtime-2026-02-10"
        return v

    @property
    def qwen_omni_model_id(self) -> str:
        normalized = (self.qwen_omni_model or "").strip().lower()
        if not normalized:
            return "qwen2.5-omni-7b"

        legacy_aliases = {
            "qwen-omni",
            "qwen-omni-realtime",
            "qwen3.5-omni-plus",
            "qwen3.5-omni-plus-realtime",
            "qwen3.5-pmni-plus",
            "qwen3.5-pmni-plus-realtime",
        }
        if normalized in legacy_aliases:
            return "qwen2.5-omni-7b"
        return normalized

    @property
    def resolved_fall_detection_target_family_ids(self) -> list[str]:
        raw = str(self.fall_detection_target_family_ids or "").strip()
        if not raw:
            return []
        return [item.strip() for item in raw.split(",") if item.strip()]

    @property
    def resolved_fall_detection_target_device_mac(self) -> str:
        configured = (self.fall_detection_target_device_mac or "").strip().upper()
        if configured:
            return configured
        camera_ip = self.camera_ip.strip()
        if camera_ip:
            return f"CAMERA-{camera_ip}".upper()
        return "CAMERA-UNKNOWN"

    @property
    def qwen_tts_model_name(self) -> str:
        return self.qwen_tts_model.strip() or "qwen3-tts-flash"

    @property
    def qwen_tts_model_id(self) -> str:
        raw = (self.qwen_tts_model.strip() or "").lower()
        if not raw:
            return "qwen3-tts-flash"
        if raw in {"qwen3-tts-flash", "qwen3-tts"}:
            return "qwen3-tts-flash"
        if raw == "qwen-tts":
            return "qwen-tts"
        return self.qwen_tts_model.strip().lower()

    @property
    def qwen_tts_voice_id(self) -> str:
        return self.qwen_tts_voice.strip() or "Serena"

    @property
    def tongyi_chat_configured(self) -> bool:
        return bool(self.dashscope_api_key and self.tongyi_chat_model)

    @property
    def tongyi_embedding_configured(self) -> bool:
        return bool(self.dashscope_api_key and self.tongyi_embedding_model)

    @property
    def tongyi_rerank_configured(self) -> bool:
        return bool(self.dashscope_api_key and self.tongyi_rerank_model)

    @property
    def preferred_llm_provider(self) -> Literal["qwen", "ollama"]:
        if self.llm_provider == "ollama":
            return "ollama"
        if self.llm_provider == "auto":
            return "qwen" if self.qwen_llm_configured else "ollama"
        return "qwen"

    @property
    def runtime_mode(self) -> Literal["mock", "serial", "mqtt"]:
        if self.data_mode == "mqtt" and self.mqtt_enabled:
            return "mqtt"
        if self.data_mode == "serial" and self.serial_enabled:
            return "serial"
        return "mock"

    @property
    def serial_runtime_enabled(self) -> bool:
        return self.runtime_mode == "serial"

    @property
    def mock_runtime_enabled(self) -> bool:
        return self.runtime_mode == "mock" and self.use_mock_data


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
