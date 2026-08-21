from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable
from urllib.parse import urlparse

import requests

from backend.config import Settings, get_settings
from backend.models.alarm_model import AlarmRecord
from backend.models.video_bridge_model import (
    VideoAnalysisIngestResponse,
    VideoAnalysisPushRequest,
    VideoBridgeFallEventRequest,
    VideoBridgeRuntimeConfigResponse,
    VideoBridgeRuntimeConfigUpdateRequest,
    VideoBridgeStatusResponse,
)
from backend.services.video_adapter import ADAPTER_VERSION, VideoAnalysisAdapter


AlarmIngestCallback = Callable[[dict[str, object]], Awaitable[AlarmRecord | None]]


class VideoBridgeService:
    """Bridge a standalone vision service into the main alarm pipeline."""

    def __init__(
        self,
        adapter: VideoAnalysisAdapter | None = None,
        *,
        settings: Settings | None = None,
        runtime_config_path: Path | None = None,
        alarm_ingest_callback: AlarmIngestCallback | None = None,
    ) -> None:
        self._adapter = adapter or VideoAnalysisAdapter()
        self._settings = settings or get_settings()
        self._records: dict[tuple[str, str], object] = {}
        self._updated_at = datetime.now(timezone.utc)
        self._session = requests.Session()
        self._runtime_config_path = runtime_config_path or (self._settings.data_dir / "video_bridge_runtime_config.json")
        self._alarm_ingest_callback = alarm_ingest_callback
        self._bridge_seen_keys: dict[str, float] = {}
        self._runtime_config = self._load_runtime_config()
        self._apply_runtime_settings(self._runtime_config)
        self._vision_service_status: dict[str, Any] = {
            "enabled": bool(self._runtime_config["poll_enabled"]),
            "base_url": self._runtime_config["base_url"],
            "camera_id": self._runtime_config["camera_id"],
            "poll_hz": self._runtime_config["poll_hz"],
            "timeout_seconds": self._runtime_config["timeout_seconds"],
            "target_device_mac": self._runtime_config["target_device_mac"],
            "target_elder_id": self._runtime_config["target_elder_id"],
            "target_family_ids": list(self._runtime_config["target_family_ids"]),
            "last_poll_at": None,
            "last_ok_at": None,
            "last_error": None,
            "health": None,
            "source": None,
            "latest_received_at": None,
            "last_promoted_at": None,
            "last_promoted_key": None,
            "last_suppression_reason": None,
            "last_source_ip": None,
        }

    def set_alarm_ingest_callback(self, callback: AlarmIngestCallback) -> None:
        self._alarm_ingest_callback = callback

    def ingest(self, payload: VideoAnalysisPushRequest) -> VideoAnalysisIngestResponse:
        record = self._adapter.normalize(payload)
        self._records[(record.camera_id, record.stream_name)] = record
        self._updated_at = record.received_at
        return VideoAnalysisIngestResponse(
            camera_id=record.camera_id,
            stream_name=record.stream_name,
            received_at=record.received_at,
            service_state=record.service_state,
            stale=record.stale,
        )

    async def poll_once_async(self) -> dict[str, Any]:
        config = self._current_runtime_config()
        base_url = str(config["base_url"]).rstrip("/")
        camera_id = str(config["camera_id"]).strip() or "camera_01"
        source_ip = self._base_url_host(base_url)
        self._vision_service_status.update(
            {
                "enabled": bool(config["poll_enabled"]),
                "base_url": base_url,
                "camera_id": camera_id,
                "poll_hz": float(config["poll_hz"]),
                "timeout_seconds": float(config["timeout_seconds"]),
                "target_device_mac": config["target_device_mac"],
                "target_elder_id": config["target_elder_id"],
                "target_family_ids": list(config["target_family_ids"]),
                "last_poll_at": datetime.now(timezone.utc).isoformat(),
                "last_source_ip": source_ip,
            }
        )

        try:
            fetched = await asyncio.to_thread(self._fetch_vision_snapshot, config)
            accepted = self.ingest(VideoAnalysisPushRequest(**fetched["payload"]))
            self._vision_service_status.update(
                {
                    "last_ok_at": datetime.now(timezone.utc).isoformat(),
                    "last_error": None,
                    "health": fetched["health"],
                    "source": fetched["source"],
                    "latest_received_at": accepted.received_at.isoformat(),
                }
            )

            promotion_result: dict[str, Any] | None = None
            if fetched["promotion_event"] is not None:
                promotion_result = await self._promote_event(
                    fetched["promotion_event"],
                    source_label="vision_service_poll",
                    source_ip=source_ip,
                )
            else:
                self._vision_service_status["last_suppression_reason"] = fetched["promotion_suppression"]

            return {
                "ok": True,
                "accepted": accepted.model_dump(mode="json"),
                "vision_service": self.vision_service_status(),
                "promotion": promotion_result,
            }
        except Exception as exc:
            self._vision_service_status["last_error"] = str(exc)
            self._vision_service_status["last_suppression_reason"] = "poll_failed"
            LOGGER.warning("Vision service polling failed: %s", exc)
            return {"ok": False, "error": str(exc), "vision_service": self.vision_service_status()}

    async def receive_fall_event_async(
        self,
        payload: VideoBridgeFallEventRequest,
        *,
        source_ip: str | None = None,
        push_token: str | None = None,
    ) -> dict[str, Any]:
        if not self.is_authorized_push(source_ip=source_ip, push_token=push_token):
            LOGGER.warning("Rejected video-bridge push from source_ip=%s", source_ip or "unknown")
            raise PermissionError("VIDEO_BRIDGE_PUSH_FORBIDDEN")

        event = self._build_fall_event_from_push(payload)
        return await self._promote_event(
            event,
            source_label="vision_service_push",
            source_ip=source_ip,
        )

    def get_vision_health(self) -> Any:
        config = self._current_runtime_config()
        base_url = str(config["base_url"]).rstrip("/")
        timeout = float(config["timeout_seconds"])
        if self._looks_like_local_camera_runtime(base_url):
            return self._get_json(f"{base_url}/api/v1/camera/health", timeout=timeout)
        return self._get_json(f"{base_url}/healthz", timeout=timeout)

    def get_vision_source(self, camera_id: str | None = None) -> Any:
        config = self._current_runtime_config()
        resolved_camera_id = (camera_id or str(config["camera_id"]) or "camera_01").strip()
        base_url = str(config["base_url"]).rstrip("/")
        timeout = float(config["timeout_seconds"])
        if self._looks_like_local_camera_runtime(base_url):
            return {
                "camera_id": resolved_camera_id,
                "source": "local_camera_runtime",
                "base_url": base_url,
                "snapshot_url": f"{base_url}/api/v1/camera/snapshot",
                "mjpeg_url": f"{base_url}/api/v1/camera/stream.mjpg",
            }
        return self._get_json_or_text(
            f"{base_url}/stream/source",
            timeout=timeout,
            params={"camera_id": resolved_camera_id},
        )

    def get_vision_latest(self, camera_id: str | None = None) -> Any:
        config = self._current_runtime_config()
        resolved_camera_id = (camera_id or str(config["camera_id"]) or "camera_01").strip()
        base_url = str(config["base_url"]).rstrip("/")
        timeout = float(config["timeout_seconds"])
        if self._looks_like_local_camera_runtime(base_url):
            health = self._get_json(f"{base_url}/api/v1/camera/health", timeout=timeout)
            return {
                "camera_id": resolved_camera_id,
                "stream_name": "primary",
                "service_state": "running" if health.get("running") else "degraded",
                "camera_lost": not bool(health.get("has_frame")),
                "capture_stale": not bool(health.get("fresh_frame")),
                "frame_age_ms": int(float(health.get("frame_age_seconds") or 0.0) * 1000),
                "stream_type": "mjpeg",
                "stream_url": f"{base_url}/api/v1/camera/stream.mjpg",
                "snapshot_url": f"{base_url}/api/v1/camera/snapshot",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "metadata": {
                    "source": "local_camera_runtime",
                    "runtime_health": health,
                },
            }
        return self._get_json(
            f"{base_url}/integration/results/{resolved_camera_id}/latest",
            timeout=timeout,
        )

    def probe_vision_stream(self, payload: dict[str, Any]) -> Any:
        config = self._current_runtime_config()
        base_url = str(config["base_url"]).rstrip("/")
        if self._looks_like_local_camera_runtime(base_url):
            return {
                "ok": True,
                "mode": "local_camera_runtime",
                "base_url": base_url,
                "payload": payload,
            }
        return self._post_json(
            f"{base_url}/stream/probe",
            payload,
            timeout=float(config["timeout_seconds"]),
        )

    def switch_vision_host(self, payload: dict[str, Any]) -> Any:
        config = self._current_runtime_config()
        base_url = str(config["base_url"]).rstrip("/")
        if self._looks_like_local_camera_runtime(base_url):
            runtime_payload = {
                "stream": "av0_1",
            }
            return self._post_json(
                f"{base_url}/api/v1/camera/stream/switch",
                runtime_payload,
                timeout=float(config["timeout_seconds"]),
            )
        return self._post_json(
            f"{base_url}/stream/switch-host",
            payload,
            timeout=float(config["timeout_seconds"]),
        )

    def runtime_config(self) -> VideoBridgeRuntimeConfigResponse:
        config = self._current_runtime_config()
        return VideoBridgeRuntimeConfigResponse(
            base_url=str(config["base_url"]),
            camera_id=str(config["camera_id"]),
            poll_enabled=bool(config["poll_enabled"]),
            poll_hz=float(config["poll_hz"]),
            timeout_seconds=float(config["timeout_seconds"]),
            push_token_set=bool(str(config["push_token"]).strip()),
            target_device_mac=str(config["target_device_mac"]),
            target_elder_id=str(config["target_elder_id"]),
            target_family_ids=list(config["target_family_ids"]),
        )

    def update_runtime_config(
        self,
        payload: VideoBridgeRuntimeConfigUpdateRequest | dict[str, Any],
    ) -> VideoBridgeRuntimeConfigResponse:
        raw_payload = payload.model_dump(exclude_none=True) if isinstance(payload, VideoBridgeRuntimeConfigUpdateRequest) else dict(payload)
        config = self._current_runtime_config()
        updated = dict(config)

        if "base_url" in raw_payload:
            updated["base_url"] = self._normalize_base_url(raw_payload["base_url"])
        if "camera_id" in raw_payload:
            updated["camera_id"] = str(raw_payload["camera_id"]).strip() or "camera_01"
        if "poll_enabled" in raw_payload:
            updated["poll_enabled"] = bool(raw_payload["poll_enabled"])
        if "poll_hz" in raw_payload:
            updated["poll_hz"] = max(0.2, min(5.0, float(raw_payload["poll_hz"])))
        if "timeout_seconds" in raw_payload:
            updated["timeout_seconds"] = max(0.5, min(30.0, float(raw_payload["timeout_seconds"])))
        if "push_token" in raw_payload:
            updated["push_token"] = str(raw_payload["push_token"] or "").strip()
        if "target_device_mac" in raw_payload:
            updated["target_device_mac"] = str(raw_payload["target_device_mac"] or "").strip().upper()
        if "target_elder_id" in raw_payload:
            updated["target_elder_id"] = str(raw_payload["target_elder_id"] or "").strip()
        if "target_family_ids" in raw_payload:
            updated["target_family_ids"] = self._normalize_family_ids(raw_payload["target_family_ids"])

        self._runtime_config = updated
        self._persist_runtime_config(updated)
        self._apply_runtime_settings(updated)
        self._vision_service_status.update(
            {
                "enabled": bool(updated["poll_enabled"]),
                "base_url": updated["base_url"],
                "camera_id": updated["camera_id"],
                "poll_hz": updated["poll_hz"],
                "timeout_seconds": updated["timeout_seconds"],
                "target_device_mac": updated["target_device_mac"],
                "target_elder_id": updated["target_elder_id"],
                "target_family_ids": list(updated["target_family_ids"]),
            }
        )
        return self.runtime_config()

    def is_authorized_push(self, *, source_ip: str | None, push_token: str | None) -> bool:
        config = self._current_runtime_config()
        configured_token = str(config["push_token"]).strip()
        configured_host = self._base_url_host(str(config["base_url"]))
        token_match = bool(configured_token and push_token and push_token.strip() == configured_token)
        ip_match = bool(configured_host and source_ip and source_ip.strip() == configured_host)
        self._vision_service_status["last_source_ip"] = source_ip
        return token_match or ip_match

    def vision_service_status(self) -> dict[str, Any]:
        current = self._current_runtime_config()
        status = dict(self._vision_service_status)
        status.update(
            {
                "enabled": bool(current["poll_enabled"]),
                "base_url": current["base_url"],
                "camera_id": current["camera_id"],
                "poll_hz": current["poll_hz"],
                "timeout_seconds": current["timeout_seconds"],
                "target_device_mac": current["target_device_mac"],
                "target_elder_id": current["target_elder_id"],
                "target_family_ids": list(current["target_family_ids"]),
            }
        )
        return status

    def status(self, *, include_mock: bool = True) -> VideoBridgeStatusResponse:
        records = list(self._records.values())
        if not records and include_mock and not self.poll_enabled():
            records = [self._adapter.mock_record()]

        records.sort(key=lambda item: item.received_at, reverse=True)
        latest = records[0] if records else None
        bridge_state = latest.service_state if latest else "unknown"
        if records and any(item.service_state in {"error", "degraded"} for item in records):
            bridge_state = "degraded"

        return VideoBridgeStatusResponse(
            bridge_state=bridge_state,
            adapter_version=ADAPTER_VERSION,
            camera_count=len(records),
            updated_at=self._updated_at,
            latest=latest,
            cameras=records,
            notes=[
                "Main system can pull standalone vision-service telemetry and promote confirmed fall events.",
                "Vision service owns RTSP and AI inference; this bridge stores latest structured results.",
            ],
            vision_service=self.vision_service_status(),
        )

    def current_poll_interval_seconds(self) -> float:
        poll_hz = float(self._current_runtime_config()["poll_hz"])
        return 1.0 / max(0.2, min(5.0, poll_hz or 2.0))

    def poll_enabled(self) -> bool:
        return bool(self._current_runtime_config()["poll_enabled"])

    def current_base_url(self) -> str:
        return str(self._current_runtime_config()["base_url"])

    def current_camera_id(self) -> str:
        return str(self._current_runtime_config()["camera_id"])

    @staticmethod
    def _looks_like_local_camera_runtime(base_url: str) -> bool:
        parsed = urlparse(base_url)
        host = (parsed.hostname or "").strip().lower()
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        return host in {"127.0.0.1", "localhost"} and port == 8090

    def _fetch_vision_snapshot(self, config: dict[str, Any]) -> dict[str, Any]:
        base_url = str(config["base_url"]).rstrip("/")
        camera_id = str(config["camera_id"]).strip() or "camera_01"
        timeout = float(config["timeout_seconds"])
        health = self._get_json(f"{base_url}/healthz", timeout=timeout)
        source = self._get_json_or_text(f"{base_url}/stream/source", timeout=timeout, params={"camera_id": camera_id})
        latest = self._get_json(f"{base_url}/integration/results/{camera_id}/latest", timeout=timeout)
        payload = self._payload_from_vision_latest(latest, camera_id=camera_id, source=source)
        promotion_event, promotion_suppression = self._promotion_event_from_latest(
            latest if isinstance(latest, dict) else {"raw": latest},
            payload=payload,
            camera_id=camera_id,
            source=source,
        )
        return {
            "health": health,
            "source": source,
            "latest": latest,
            "payload": payload,
            "promotion_event": promotion_event,
            "promotion_suppression": promotion_suppression,
        }

    async def _promote_event(
        self,
        event: dict[str, object],
        *,
        source_label: str,
        source_ip: str | None,
    ) -> dict[str, Any]:
        if self._alarm_ingest_callback is None:
            self._vision_service_status["last_suppression_reason"] = "alarm_ingest_not_configured"
            return {"promoted": False, "reason": "alarm_ingest_not_configured"}

        now_monotonic = time.monotonic()
        self._expire_seen_keys(now_monotonic)
        dedupe_key = self._bridge_dedupe_key(event)
        if dedupe_key:
            dedupe_window_seconds = max(1.0, float(self._settings.fall_detection_incident_reopen_seconds or 10.0))
            previous_seen_at = self._bridge_seen_keys.get(dedupe_key)
            if previous_seen_at is not None and now_monotonic - previous_seen_at < dedupe_window_seconds:
                self._vision_service_status.update(
                    {
                        "last_source_ip": source_ip,
                        "last_promoted_key": dedupe_key,
                        "last_suppression_reason": "bridge_dedupe",
                    }
                )
                return {"promoted": False, "suppressed": True, "reason": "bridge_dedupe", "dedupe_key": dedupe_key}

        event = self._apply_bridge_target_context(event)
        alarm = await self._alarm_ingest_callback(event)
        if dedupe_key:
            self._bridge_seen_keys[dedupe_key] = now_monotonic

        promoted_at = datetime.now(timezone.utc).isoformat()
        self._vision_service_status.update(
            {
                "last_source_ip": source_ip,
                "last_promoted_at": promoted_at,
                "last_promoted_key": dedupe_key,
                "last_suppression_reason": None if alarm is not None else "alarm_not_created",
            }
        )
        return {
            "promoted": alarm is not None,
            "suppressed": alarm is None,
            "reason": None if alarm is not None else "alarm_not_created",
            "dedupe_key": dedupe_key,
            "alarm_id": alarm.id if alarm is not None else None,
            "alarm_type": alarm.alarm_type.value if alarm is not None else None,
            "alarm": alarm,
        }

    def _build_fall_event_from_push(self, payload: VideoBridgeFallEventRequest) -> dict[str, object]:
        now = datetime.now(timezone.utc)
        timestamp_slug = now.strftime("%Y%m%d%H%M%S%f")
        camera_id = payload.camera_id.strip()
        stream_name = payload.stream_name.strip() or "primary"
        fall_prob = self._clamp_probability(payload.fall_score if payload.fall_score is not None else payload.fall_prob)
        risk = payload.risk
        severity = (payload.severity or "").strip().upper()
        if not severity:
            severity = "L3" if risk in {"high", "critical"} or fall_prob >= 0.82 else "L2"

        snapshot_url = (
            (payload.snapshot_url or "").strip()
            or (payload.snapshot_path or "").strip()
            or "/api/v1/camera/processed-snapshot"
        )
        track_id = (payload.track_id or "").strip() or f"video-bridge-{camera_id}-{timestamp_slug}"
        incident_id = (payload.incident_id or "").strip() or f"video-bridge-fall-{camera_id}-{timestamp_slug}"

        event = payload.model_dump(mode="json", exclude_none=True)
        event.update(
            {
                "source": (payload.source or "vision_service").strip() or "vision_service",
                "demo": bool(payload.demo),
                "event_type": (payload.event_type or "fall_confirmed").strip() or "fall_confirmed",
                "state": (payload.state or "confirmed_fall").strip() or "confirmed_fall",
                "status": (payload.status or payload.state or "confirmed_fall").strip(),
                "severity": severity,
                "risk": risk,
                "risk_level": payload.risk_level or risk,
                "fall_detected": bool(payload.fall_detected),
                "fall_score": fall_prob,
                "fall_prob": fall_prob,
                "camera_id": camera_id,
                "stream_name": stream_name,
                "service_state": payload.service_state,
                "track_id": track_id,
                "incident_id": incident_id,
                "snapshot_url": snapshot_url,
                "snapshot_path": snapshot_url,
                "timestamp": payload.timestamp.isoformat(),
            }
        )

        scores = dict(payload.scores) if isinstance(payload.scores, dict) else {}
        scores.setdefault("video_bridge", fall_prob)
        scores.setdefault("detector", fall_prob)
        scores.setdefault("posture", max(0.72, fall_prob))
        scores.setdefault("hybrid", fall_prob)
        event["scores"] = scores

        injury = dict(payload.injury) if isinstance(payload.injury, dict) else {}
        injury.setdefault("level", "I3" if severity == "L3" else "I2")
        injury.setdefault("reason", "video_bridge_fall_event")
        injury.setdefault("down_seconds", 4.2)
        injury.setdefault("advice", "Please inspect the live camera view immediately and confirm the elder's condition.")
        event["injury"] = injury

        metadata = dict(payload.metadata) if isinstance(payload.metadata, dict) else {}
        metadata.setdefault("trigger", "video_bridge_fall_events")
        metadata.setdefault("received_at", now.isoformat())
        event["metadata"] = metadata
        return event

    def _promotion_event_from_latest(
        self,
        latest: dict[str, Any],
        *,
        payload: dict[str, Any],
        camera_id: str,
        source: Any,
    ) -> tuple[dict[str, object] | None, str | None]:
        capture_stale = bool(payload.get("capture_stale"))
        if capture_stale:
            return None, "capture_stale"

        service_state = str(payload.get("service_state") or "unknown").strip().lower()
        if service_state in {"error", "stopped", "unknown"}:
            return None, "service_unavailable"

        state = str(
            latest.get("state")
            or latest.get("fall_state")
            or payload.get("fall_state")
            or ""
        ).strip().lower()
        status = str(latest.get("status") or state or "").strip().lower()
        fall_detected = bool(self._coerce_bool(self._first_present(latest, payload, keys=("fall_detected",))))
        alarm_confirmed = bool(
            self._coerce_bool(self._first_present(latest, payload, keys=("alarm_confirmed", "confirmed_fall")))
        )
        fall_score = self._coerce_float(
            latest.get("fall_score")
            or latest.get("fall_prob")
            or payload.get("fall_prob")
            or (latest.get("scores") or {}).get("fall")
            if isinstance(latest.get("scores"), dict)
            else None
        ) or 0.0
        threshold = max(0.0, min(1.0, float(self._settings.fall_detection_min_alert_score or 0.0)))
        confirmed_states = {"confirmed_fall", "fallen", "abnormal_recovery", "needs_assistance", "emergency"}
        score_triggered = threshold > 0.0 and fall_score >= threshold
        should_promote = (
            alarm_confirmed
            or
            state in confirmed_states
            or status in confirmed_states
            or fall_detected
            or score_triggered
        )
        if not should_promote:
            return None, "not_candidate"

        severity = str(latest.get("severity") or "").strip().upper()
        if not severity:
            severity = "L3" if state in {"abnormal_recovery", "needs_assistance", "emergency"} or fall_score >= 0.82 else "L2"

        injury = dict(latest.get("injury") or {}) if isinstance(latest.get("injury"), dict) else {}
        injury.setdefault("level", "I3" if severity == "L3" else "I2")
        injury.setdefault("reason", "vision_service_poll")
        injury.setdefault("advice", "Please inspect the live camera view immediately and confirm the elder's condition.")
        event_timestamp = self._coerce_timestamp(latest.get("timestamp") or payload.get("timestamp")).isoformat()
        track_id = str(
            latest.get("track_id")
            or latest.get("id")
            or payload.get("track_id")
            or f"vision-track-{camera_id}"
        ).strip()
        payload_metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
        incident_id = str(
            latest.get("incident_id")
            or payload_metadata.get("incident_id")
            or f"vision-fall-{camera_id}-{track_id}"
        ).strip()
        snapshot_url = str(latest.get("snapshot_url") or payload.get("snapshot_url") or "").strip()
        if not snapshot_url:
            snapshot_url = "/api/v1/camera/processed-snapshot"

        metadata = dict(payload.get("metadata") or {}) if isinstance(payload.get("metadata"), dict) else {}
        metadata["raw"] = latest
        metadata["source_status"] = source
        metadata["trigger"] = "vision_service_poll"

        event: dict[str, object] = {
            "source": "vision_service",
            "event_type": "fall_confirmed",
            "state": state or "confirmed_fall",
            "status": status or state or "confirmed_fall",
            "service_state": payload.get("service_state") or "running",
            "severity": severity,
            "risk": latest.get("risk") or payload.get("risk") or ("high" if severity == "L3" else "medium"),
            "risk_level": latest.get("risk_level") or latest.get("risk") or payload.get("risk") or ("high" if severity == "L3" else "medium"),
            "fall_detected": True if alarm_confirmed or fall_detected or state in confirmed_states else score_triggered,
            "fall_score": fall_score,
            "fall_prob": fall_score,
            "camera_id": camera_id,
            "stream_name": payload.get("stream_name") or "analysis",
            "track_id": track_id,
            "incident_id": incident_id,
            "bbox": latest.get("bbox") or payload.get("bbox"),
            "target": latest.get("target") or payload.get("target"),
            "snapshot_url": snapshot_url,
            "snapshot_path": snapshot_url,
            "timestamp": event_timestamp,
            "scores": dict(latest.get("scores") or {}) if isinstance(latest.get("scores"), dict) else {
                "video_bridge": fall_score,
                "detector": fall_score,
                "posture": fall_score,
                "hybrid": fall_score,
            },
            "injury": injury,
            "metadata": metadata,
        }
        return event, None

    def _apply_bridge_target_context(self, event: dict[str, object]) -> dict[str, object]:
        metadata = dict(event.get("metadata") or {}) if isinstance(event.get("metadata"), dict) else {}
        target_device_mac = str(self._current_runtime_config()["target_device_mac"]).strip().upper()
        target_elder_id = str(self._current_runtime_config()["target_elder_id"]).strip()
        target_family_ids = list(self._current_runtime_config()["target_family_ids"])
        if target_device_mac:
            metadata.setdefault("target_device_mac", target_device_mac)
        if target_elder_id:
            metadata.setdefault("elder_id", target_elder_id)
        if target_family_ids:
            metadata.setdefault("family_ids", target_family_ids)
        event["metadata"] = metadata
        return event

    def _default_runtime_config(self) -> dict[str, Any]:
        return {
            "base_url": self._normalize_base_url(self._settings.vision_service_base_url),
            "camera_id": (self._settings.vision_service_camera_id or "camera_01").strip() or "camera_01",
            "poll_enabled": bool(self._settings.vision_service_poll_enabled),
            "poll_hz": max(0.2, min(5.0, float(self._settings.vision_service_poll_hz or 2.0))),
            "timeout_seconds": max(0.5, min(30.0, float(self._settings.vision_service_timeout_seconds or 2.5))),
            "push_token": "",
            "target_device_mac": (self._settings.fall_detection_target_device_mac or self._settings.resolved_fall_detection_target_device_mac).strip().upper(),
            "target_elder_id": (self._settings.fall_detection_target_elder_id or "").strip(),
            "target_family_ids": self._normalize_family_ids(self._settings.fall_detection_target_family_ids),
        }

    def _load_runtime_config(self) -> dict[str, Any]:
        config = self._default_runtime_config()
        if not self._runtime_config_path.exists():
            return config
        try:
            payload = json.loads(self._runtime_config_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            LOGGER.warning("Failed to read video bridge runtime config: %s", exc)
            return config

        if isinstance(payload, dict):
            if "base_url" in payload:
                config["base_url"] = self._normalize_base_url(payload.get("base_url"))
            if "camera_id" in payload:
                config["camera_id"] = str(payload.get("camera_id") or "camera_01").strip() or "camera_01"
            if "poll_enabled" in payload:
                config["poll_enabled"] = bool(payload.get("poll_enabled"))
            if "poll_hz" in payload:
                config["poll_hz"] = max(0.2, min(5.0, float(payload.get("poll_hz") or 2.0)))
            if "timeout_seconds" in payload:
                config["timeout_seconds"] = max(0.5, min(30.0, float(payload.get("timeout_seconds") or 2.5)))
            if "push_token" in payload:
                config["push_token"] = str(payload.get("push_token") or "").strip()
            if "target_device_mac" in payload:
                config["target_device_mac"] = str(payload.get("target_device_mac") or "").strip().upper()
            if "target_elder_id" in payload:
                config["target_elder_id"] = str(payload.get("target_elder_id") or "").strip()
            if "target_family_ids" in payload:
                config["target_family_ids"] = self._normalize_family_ids(payload.get("target_family_ids"))
        return config

    def _persist_runtime_config(self, config: dict[str, Any]) -> None:
        self._runtime_config_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "base_url": config["base_url"],
            "camera_id": config["camera_id"],
            "poll_enabled": config["poll_enabled"],
            "poll_hz": config["poll_hz"],
            "timeout_seconds": config["timeout_seconds"],
            "push_token": config["push_token"],
            "target_device_mac": config["target_device_mac"],
            "target_elder_id": config["target_elder_id"],
            "target_family_ids": list(config["target_family_ids"]),
        }
        self._runtime_config_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _apply_runtime_settings(self, config: dict[str, Any]) -> None:
        self._settings.vision_service_base_url = str(config["base_url"])
        self._settings.vision_service_camera_id = str(config["camera_id"])
        self._settings.vision_service_poll_enabled = bool(config["poll_enabled"])
        self._settings.vision_service_poll_hz = float(config["poll_hz"])
        self._settings.vision_service_timeout_seconds = float(config["timeout_seconds"])
        self._settings.fall_detection_target_device_mac = str(config["target_device_mac"])
        self._settings.fall_detection_target_elder_id = str(config["target_elder_id"])
        self._settings.fall_detection_target_family_ids = ",".join(config["target_family_ids"])

    def _current_runtime_config(self) -> dict[str, Any]:
        return dict(self._runtime_config)

    def _expire_seen_keys(self, now_monotonic: float) -> None:
        ttl_seconds = max(1.0, float(self._settings.fall_detection_incident_reopen_seconds or 10.0))
        expired = [
            key
            for key, seen_at in self._bridge_seen_keys.items()
            if now_monotonic - seen_at >= ttl_seconds
        ]
        for key in expired:
            self._bridge_seen_keys.pop(key, None)

    def _bridge_dedupe_key(self, event: dict[str, object]) -> str | None:
        incident_id = str(event.get("incident_id") or "").strip()
        if incident_id:
            return f"incident:{incident_id}"
        camera_id = str(event.get("camera_id") or "").strip()
        track_id = str(event.get("track_id") or "").strip()
        if camera_id and track_id:
            return f"camera_track:{camera_id}:{track_id}"
        snapshot_url = str(event.get("snapshot_url") or event.get("snapshot_path") or "").strip()
        state = str(event.get("state") or "").strip()
        if camera_id and snapshot_url and state:
            return f"camera_snapshot_state:{camera_id}:{snapshot_url}:{state}"
        return None

    def _get_json(self, url: str, *, timeout: float, params: dict[str, Any] | None = None) -> Any:
        response = self._session.get(url, params=params, timeout=timeout)
        response.raise_for_status()
        return response.json()

    def _get_json_or_text(self, url: str, *, timeout: float, params: dict[str, Any] | None = None) -> Any:
        response = self._session.get(url, params=params, timeout=timeout)
        response.raise_for_status()
        content_type = response.headers.get("content-type", "")
        if "json" in content_type.lower():
            return response.json()
        text = response.text
        parsed: dict[str, str] = {}
        for raw_line in text.splitlines():
            key, separator, value = raw_line.partition(":")
            if separator and key.strip():
                parsed[key.strip()] = value.strip()
        return parsed or text

    def _post_json(self, url: str, payload: dict[str, Any], *, timeout: float) -> Any:
        response = self._session.post(url, json=payload, timeout=timeout)
        response.raise_for_status()
        content_type = response.headers.get("content-type", "")
        if "json" in content_type.lower():
            return response.json()
        return response.text

    def _payload_from_vision_latest(self, latest: Any, *, camera_id: str, source: Any) -> dict[str, Any]:
        data = latest if isinstance(latest, dict) else {"raw": latest}
        track = self._select_primary_track(data)
        track_id = self._first_present(track, data, keys=("track_id", "id"))
        bbox = self._coerce_bbox(self._first_present(track, data, keys=("bbox", "box")))
        pose = track.get("pose") if isinstance(track.get("pose"), dict) else data.get("pose")
        keypoints = pose.get("keypoints") if isinstance(pose, dict) else None
        frame_age_ms = self._coerce_int(data.get("frame_age_ms") or data.get("age_ms"))
        display_source = data.get("display_source") or self._source_value(source, "display_source_current")
        analysis_source = data.get("analysis_source") or "analysis"
        is_target = bool(self._first_present(track, data, keys=("is_target", "target_matched")) or False)
        fall_prob = self._coerce_float(
            self._first_present(track, data, keys=("fall_prob", "fall_score", "score", "confidence"))
        )
        fall_state = self._fall_state_from_payload(data, track)

        return {
            "camera_id": str(data.get("camera_id") or camera_id),
            "stream_name": str(analysis_source or "analysis"),
            "service_state": "running",
            "camera_lost": False,
            "capture_stale": bool(frame_age_ms is not None and frame_age_ms >= 3000),
            "frame_age_ms": frame_age_ms,
            "video_fps": self._coerce_float(data.get("video_fps") or data.get("source_fps")),
            "overlay_fps": self._coerce_float(data.get("overlay_fps") or data.get("analysis_fps")),
            "ws_fps": self._coerce_float(data.get("ws_fps")),
            "stream_type": "unknown",
            "stream_url": None,
            "track_id": str(track_id) if track_id is not None else None,
            "bbox": bbox,
            "target": {
                "target_id": str(track_id) if track_id is not None else None,
                "label": "target" if is_target else "person",
                "matched": is_target,
                "confidence": self._coerce_float(self._first_present(track, data, keys=("target_score", "confidence"))),
                "metadata": {"is_target": is_target},
            },
            "fall_state": fall_state,
            "risk": "high" if fall_state in {"confirmed_fall", "fallen"} else "low",
            "fall_prob": fall_prob,
            "snapshot_url": data.get("snapshot_url"),
            "timestamp": self._coerce_timestamp(data.get("timestamp") or data.get("ts")),
            "metadata": {
                "source": "vision_service_pull",
                "display_source": display_source,
                "analysis_source": analysis_source,
                "pose_keypoint_count": len(keypoints) if isinstance(keypoints, list) else 0,
                "pose": pose if isinstance(pose, dict) else None,
                "source_status": source,
                "raw": data,
            },
        }

    @staticmethod
    def _select_primary_track(data: dict[str, Any]) -> dict[str, Any]:
        objects = data.get("objects") or data.get("tracks") or data.get("detections")
        if isinstance(objects, list) and objects:
            target = next((item for item in objects if isinstance(item, dict) and item.get("is_target")), None)
            if isinstance(target, dict):
                return target
            first = objects[0]
            return first if isinstance(first, dict) else {}
        return data

    @staticmethod
    def _first_present(*containers: dict[str, Any], keys: tuple[str, ...]) -> Any:
        for container in containers:
            for key in keys:
                value = container.get(key)
                if value is not None:
                    return value
        return None

    @staticmethod
    def _coerce_bbox(value: Any) -> list[float] | None:
        if not isinstance(value, list) or len(value) < 4:
            return None
        try:
            return [float(item) for item in value[:4]]
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _coerce_float(value: Any) -> float | None:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _coerce_int(value: Any) -> int | None:
        if value is None:
            return None
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _coerce_bool(value: Any) -> bool | None:
        if value is None:
            return None
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"true", "1", "yes", "y", "on"}:
                return True
            if normalized in {"false", "0", "no", "n", "off"}:
                return False
        return None

    @staticmethod
    def _coerce_timestamp(value: Any) -> datetime:
        if isinstance(value, datetime):
            return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        if isinstance(value, (int, float)):
            seconds = float(value)
            if seconds > 10_000_000_000:
                seconds = seconds / 1000.0
            return datetime.fromtimestamp(seconds, tz=timezone.utc)
        if isinstance(value, str) and value.strip():
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
                return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
            except ValueError:
                pass
        return datetime.now(timezone.utc)

    @staticmethod
    def _source_value(source: Any, key: str) -> Any:
        if isinstance(source, dict):
            return source.get(key)
        return None

    @staticmethod
    def _fall_state_from_payload(data: dict[str, Any], track: dict[str, Any]) -> str:
        raw = str(data.get("fall_state") or data.get("state") or track.get("fall_state") or track.get("state") or "normal")
        normalized = raw.strip().lower()
        if normalized in {"confirmed_fall", "fallen", "suspected_fall", "recovery", "normal", "error"}:
            return normalized
        if "fall" in normalized:
            return "confirmed_fall"
        return "normal"

    @staticmethod
    def _normalize_family_ids(value: list[str] | str | None) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            candidates = value.split(",")
        else:
            candidates = [str(item) for item in value]
        normalized: list[str] = []
        for item in candidates:
            cleaned = str(item).strip()
            if cleaned and cleaned not in normalized:
                normalized.append(cleaned)
        return normalized

    @staticmethod
    def _normalize_base_url(value: Any) -> str:
        cleaned = str(value or "").strip()
        if not cleaned:
            return "http://127.0.0.1:8000"
        return cleaned.rstrip("/")

    @staticmethod
    def _base_url_host(base_url: str) -> str | None:
        parsed = urlparse(base_url)
        host = (parsed.hostname or "").strip()
        return host or None

    @staticmethod
    def _clamp_probability(value: float | None, *, default: float = 0.91) -> float:
        if value is None:
            value = default
        return max(0.0, min(1.0, float(value)))


LOGGER = logging.getLogger(__name__)
