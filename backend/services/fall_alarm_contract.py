from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from backend.models.alarm_model import AlarmRecord, AlarmType


FALL_ALARM_TYPES = frozenset(
    {
        AlarmType.FALL_DETECTED,
        AlarmType.FALL_INJURY_RISK,
        AlarmType.VIDEO_FALL,
    }
)
_SERIOUS_SEVERITIES = {"L3", "L4", "L5"}
_SERIOUS_INJURY_LEVELS = {"I3", "I4", "I5"}


def is_fall_alarm_type(alarm_type: AlarmType | str | None) -> bool:
    if alarm_type is None:
        return False
    raw_value = alarm_type.value if isinstance(alarm_type, AlarmType) else str(alarm_type).strip()
    return raw_value in {member.value for member in FALL_ALARM_TYPES}


def select_fall_alarm_type(
    event: Mapping[str, Any] | None,
    metadata: Mapping[str, Any] | None = None,
) -> AlarmType:
    metadata_dict = _as_dict(metadata)
    event_dict = _as_dict(event)
    explicit_type = str(
        event_dict.get("alarm_type")
        or metadata_dict.get("alarm_type")
        or metadata_dict.get("legacy_alarm_type")
        or ""
    ).strip()
    if explicit_type == AlarmType.FALL_INJURY_RISK.value:
        return AlarmType.FALL_INJURY_RISK
    if explicit_type == AlarmType.FALL_DETECTED.value:
        return AlarmType.FALL_DETECTED

    severity = str(event_dict.get("severity") or "").strip().upper()
    state = str(event_dict.get("state") or event_dict.get("status") or "").strip().lower()
    injury_level = str(_as_dict(event_dict.get("injury")).get("level") or "").strip().upper()
    if (
        severity in _SERIOUS_SEVERITIES
        or injury_level in _SERIOUS_INJURY_LEVELS
        or state in {"needs_assistance", "emergency", "abnormal_recovery"}
    ):
        return AlarmType.FALL_INJURY_RISK
    return AlarmType.FALL_DETECTED


def normalize_fall_event_payload(
    event: Mapping[str, Any] | None,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    event_dict = _as_dict(event)
    metadata_dict = _as_dict(metadata)
    raw_event = _as_dict(event_dict.get("raw_event"))
    existing_event = _as_dict(metadata_dict.get("event"))
    merged_event = {
        **raw_event,
        **event_dict,
        **existing_event,
    }

    injury = dict(merged_event.get("injury") or {}) if isinstance(merged_event.get("injury"), Mapping) else {}
    review = _as_dict(merged_event.get("multimodal_review"))
    snapshot_url = str(
        merged_event.get("snapshot_url")
        or merged_event.get("snapshot_path")
        or metadata_dict.get("snapshot_url")
        or metadata_dict.get("snapshot_path")
        or ""
    ).strip()
    state = str(merged_event.get("state") or metadata_dict.get("state") or "").strip() or "confirmed_fall"
    status = str(merged_event.get("status") or state).strip() or state
    severity = str(merged_event.get("severity") or metadata_dict.get("severity") or "").strip().upper()
    risk_level = str(
        merged_event.get("risk_level")
        or merged_event.get("risk")
        or metadata_dict.get("risk_level")
        or metadata_dict.get("risk")
        or ""
    ).strip() or "high"
    timestamp = str(
        merged_event.get("timestamp")
        or metadata_dict.get("timestamp")
        or ""
    ).strip()

    return {
        "incident_id": str(merged_event.get("incident_id") or metadata_dict.get("incident_id") or "").strip(),
        "state": state,
        "status": status,
        "snapshot_path": snapshot_url,
        "snapshot_url": snapshot_url,
        "injury": injury,
        "severity": severity,
        "multimodal_review": review,
        "camera_id": str(merged_event.get("camera_id") or metadata_dict.get("camera_id") or "").strip(),
        "fall_score": _coerce_float(
            merged_event.get("fall_score")
            if merged_event.get("fall_score") is not None
            else metadata_dict.get("fall_score")
        ),
        "fall_prob": _coerce_float(
            merged_event.get("fall_prob")
            if merged_event.get("fall_prob") is not None
            else metadata_dict.get("fall_prob")
        ),
        "risk_level": risk_level,
        "risk": risk_level,
        "timestamp": timestamp,
        "event_type": str(merged_event.get("event_type") or metadata_dict.get("event_type") or "fall_confirmed").strip(),
        "source": str(merged_event.get("source") or metadata_dict.get("source") or "vision_service").strip(),
        "service_state": str(merged_event.get("service_state") or metadata_dict.get("service_state") or "running").strip(),
        "stream_name": str(merged_event.get("stream_name") or metadata_dict.get("stream_name") or "primary").strip(),
        "track_id": str(merged_event.get("track_id") or metadata_dict.get("track_id") or "").strip(),
        "bbox": merged_event.get("bbox"),
        "target": merged_event.get("target"),
    }


def normalize_fall_alarm_metadata(
    metadata: Mapping[str, Any] | None,
    event: Mapping[str, Any] | None,
    *,
    fallback_timestamp: datetime | None = None,
) -> dict[str, Any]:
    metadata_dict = dict(_as_dict(metadata))
    event_dict = _as_dict(event)
    normalized_event = normalize_fall_event_payload(event_dict, metadata_dict)
    if not normalized_event.get("timestamp") and fallback_timestamp is not None:
        normalized_event["timestamp"] = fallback_timestamp.astimezone(timezone.utc).isoformat()

    raw_event = _as_dict(event_dict) or _as_dict(metadata_dict.get("raw_event")) or dict(normalized_event)
    metadata_dict["event"] = normalized_event
    metadata_dict["raw_event"] = raw_event
    metadata_dict["camera_id"] = normalized_event.get("camera_id") or metadata_dict.get("camera_id")
    metadata_dict["incident_id"] = normalized_event.get("incident_id") or metadata_dict.get("incident_id")
    metadata_dict["snapshot_url"] = normalized_event.get("snapshot_url") or metadata_dict.get("snapshot_url")
    metadata_dict["snapshot_path"] = normalized_event.get("snapshot_path") or metadata_dict.get("snapshot_path")
    metadata_dict["state"] = normalized_event.get("state") or metadata_dict.get("state")
    metadata_dict["risk_level"] = normalized_event.get("risk_level") or metadata_dict.get("risk_level")
    metadata_dict["risk"] = normalized_event.get("risk") or metadata_dict.get("risk")
    metadata_dict["fall_score"] = normalized_event.get("fall_score")
    metadata_dict["fall_prob"] = normalized_event.get("fall_prob")
    return metadata_dict


def normalize_fall_alarm_record(alarm: AlarmRecord) -> AlarmRecord:
    if not is_fall_alarm_type(alarm.alarm_type):
        return alarm
    normalized_metadata = normalize_fall_alarm_metadata(
        alarm.metadata,
        _as_dict(alarm.metadata.get("event")) or _as_dict(alarm.metadata.get("raw_event")) or alarm.metadata,
        fallback_timestamp=alarm.created_at,
    )
    return alarm.model_copy(update={"metadata": normalized_metadata})


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _coerce_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
