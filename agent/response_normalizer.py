from __future__ import annotations

import re
from typing import Any


_META_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"^as\s+an?\s+ai",
        r"^based\s+on\s+your\s+prompt",
        r"^i(?:'| a)?ll\s+break\s+this\s+down",
        r"^here(?:'| i)?s\s+(?:the\s+)?result",
        r"^analysis$",
        r"^###\s*(analysis|business context|tool results|model results|degraded notes)\b",
        r"^\s*(tool results|model results|business context|degraded notes)\s*:?\s*$",
        r"^\s*(system|user)\s*prompt\s*:?$",
        r"^\s*prompt\s*:?$",
        r"^\s*role\s*:?$",
        r"^\s*mode\s*:?$",
        r"^\s*tool\s*:?$",
        r"^\s*reasoning\s*:?$",
        r"^以下是分析",
        r"^下面是分析",
        r"^作为.?ai",
        r"^我是.?ai",
    ]
]

_INTERNAL_FIELD_NAME = (
    r"analysis_context|context_bundle|tool_results|model_results|degraded_notes|"
    r"retrieval_query|final_payload|prompt_text|knowledge_hits|selected_mode|"
    r"network_online|request_id|operator_role|community_id|target_device_macs|target_device_mac"
)
_INTERNAL_FIELD_PATTERN = re.compile(rf"\b({_INTERNAL_FIELD_NAME})\b", re.IGNORECASE)
_INTERNAL_FIELD_TRAILING_PATTERN = re.compile(rf"\b({_INTERNAL_FIELD_NAME})\b\s*:?.*$", re.IGNORECASE)

_BULLET_PREFIX_PATTERN = re.compile(r"^\s*(?:[-*•]+|\d+\.)\s+")
_MARKDOWN_EMPHASIS_PATTERN = re.compile(r"(\*\*|__|\*)")


def _clean_line(line: str) -> str:
    text = line.strip()
    if not text:
        return ""

    text = _BULLET_PREFIX_PATTERN.sub("", text)
    if text.startswith("```") or text in {"{", "}", "[", "]"}:
        return ""

    if _INTERNAL_FIELD_PATTERN.search(text):
        text = _INTERNAL_FIELD_TRAILING_PATTERN.sub("", text).strip(" \n:-")
        if not text:
            return ""

    if any(pattern.search(text) for pattern in _META_PATTERNS):
        return ""

    if re.fullmatch(r'["\']?[A-Za-z0-9_]+["\']?\s*:\s*[\[{].*', text):
        return ""

    return text


def sanitize_text(value: Any) -> str:
    if value is None:
        return ""

    text = str(value)
    text = text.replace("\ufeff", "").replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"`{1,3}", "", text)
    text = _MARKDOWN_EMPHASIS_PATTERN.sub("", text)
    text = re.sub(r"^#{1,6}\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*(?:[-*•]+|\d+\.)\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"\n{3,}", "\n\n", text)

    lines = [_clean_line(line) for line in text.split("\n")]
    cleaned = "\n".join(line for line in lines if line)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip(" \n:-")
    return cleaned


def sanitize_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []

    items: list[str] = []
    seen: set[str] = set()
    for raw in value:
        cleaned = sanitize_text(raw)
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        items.append(cleaned)
    return items


def _sanitize_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def _sanitize_priority_devices(value: Any) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []

    items: list[dict[str, object]] = []
    seen: set[tuple[str, str]] = set()
    for raw in value:
        if not isinstance(raw, dict):
            continue
        device_mac = sanitize_text(raw.get("device_mac"))
        risk_level = sanitize_text(raw.get("risk_level"))
        notable_events = sanitize_list(raw.get("notable_events"))
        if not device_mac:
            continue

        dedupe_key = (device_mac, risk_level)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)

        item: dict[str, object] = {"device_mac": device_mac}
        if risk_level:
            item["risk_level"] = risk_level
        if notable_events:
            item["notable_events"] = notable_events
        items.append(item)
    return items


def _sanitize_risk_distribution(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}

    cleaned: dict[str, int] = {}
    for key in ("high", "medium", "low"):
        normalized = _sanitize_int(value.get(key))
        if normalized is not None:
            cleaned[key] = normalized
    return cleaned


def _sanitize_attachment_payload(value: Any) -> dict[str, object]:
    if not isinstance(value, dict):
        return {}
    return {
        str(key): item
        for key, item in value.items()
        if isinstance(key, str)
    }


def sanitize_attachments(value: Any) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []

    items: list[dict[str, object]] = []
    seen: set[str] = set()
    for raw in value:
        if not isinstance(raw, dict):
            continue
        attachment_id = sanitize_text(raw.get("id")) or sanitize_text(raw.get("title"))
        render_type = sanitize_text(raw.get("render_type"))
        title = sanitize_text(raw.get("title"))
        if not attachment_id or not render_type or not title:
            continue
        if attachment_id in seen:
            continue
        seen.add(attachment_id)
        items.append(
            {
                "id": attachment_id,
                "title": title,
                "summary": sanitize_text(raw.get("summary")),
                "render_type": render_type,
                "render_payload": _sanitize_attachment_payload(raw.get("render_payload")),
                "source_tool": sanitize_text(raw.get("source_tool")),
            }
        )
    return items


def normalize_analysis(payload: Any) -> dict[str, object]:
    if not isinstance(payload, dict):
        return {
            "risk_flags": [],
            "recommendations": [],
            "notable_events": [],
        }

    normalized: dict[str, object] = {
        "risk_flags": sanitize_list(payload.get("risk_flags")),
        "recommendations": sanitize_list(payload.get("recommendations")),
        "notable_events": sanitize_list(payload.get("notable_events")),
    }

    risk_level = sanitize_text(payload.get("risk_level"))
    if risk_level:
        normalized["risk_level"] = risk_level

    device_count = _sanitize_int(payload.get("device_count"))
    if device_count is not None:
        normalized["device_count"] = device_count

    risk_distribution = _sanitize_risk_distribution(payload.get("risk_distribution"))
    if risk_distribution:
        normalized["risk_distribution"] = risk_distribution

    priority_devices = _sanitize_priority_devices(payload.get("priority_devices"))
    if priority_devices:
        normalized["priority_devices"] = priority_devices

    return normalized


def _fallback_answer_from_analysis(analysis: dict[str, object]) -> str:
    recommendations = sanitize_list(analysis.get("recommendations"))
    notable_events = sanitize_list(analysis.get("notable_events"))
    risk_flags = sanitize_list(analysis.get("risk_flags"))

    parts: list[str] = []
    if notable_events:
        parts.append(notable_events[0])
    if recommendations:
        parts.append(f"建议：{recommendations[0]}")
    elif risk_flags:
        parts.append(f"重点风险：{risk_flags[0]}")
    return " ".join(parts).strip()


def sanitize_agent_response(payload: dict[str, Any]) -> dict[str, object]:
    analysis = normalize_analysis(payload.get("analysis"))
    answer = sanitize_text(payload.get("answer"))
    if answer.lower() == "analysis":
        answer = ""
    if not answer:
        answer = _fallback_answer_from_analysis(analysis)
    if not answer:
        answer = "当前没有可展示的智能体结论。"

    return {
        "scope": sanitize_text(payload.get("scope")) or "community",
        "answer": answer,
        "analysis": analysis,
        "references": sanitize_list(payload.get("references")),
        "attachments": sanitize_attachments(payload.get("attachments")),
        "window": sanitize_text(payload.get("window")),
        "subject": payload.get("subject") if isinstance(payload.get("subject"), dict) else None,
        "mode": sanitize_text(payload.get("mode")),
        "selected_provider": sanitize_text(payload.get("selected_provider")),
        "selected_model": sanitize_text(payload.get("selected_model")),
        "degraded": sanitize_list(payload.get("degraded")),
    }


def _sanitize_metric_item(value: Any) -> dict[str, object] | None:
    if not isinstance(value, dict):
        return None

    item: dict[str, object] = {}
    for key in ("latest", "average", "min", "max"):
        metric_value = value.get(key)
        if isinstance(metric_value, bool):
            continue
        if isinstance(metric_value, (int, float)):
            item[key] = metric_value

    trend = sanitize_text(value.get("trend"))
    if trend:
        item["trend"] = trend

    return item or None


def sanitize_device_health_report(payload: dict[str, Any]) -> dict[str, object]:
    summary = sanitize_text(payload.get("summary"))
    risk_flags = sanitize_list(payload.get("risk_flags"))
    key_findings = sanitize_list(payload.get("key_findings"))
    recommendations = sanitize_list(payload.get("recommendations"))
    references = sanitize_list(payload.get("references"))

    if not summary:
        summary = _fallback_answer_from_analysis(
            {
                "risk_flags": risk_flags,
                "notable_events": key_findings,
                "recommendations": recommendations,
            }
        )
    if not summary:
        summary = "当前没有可展示的时间段健康报告摘要。"

    raw_period = payload.get("period")
    period = raw_period if isinstance(raw_period, dict) else {}

    metrics: dict[str, object] = {}
    raw_metrics = payload.get("metrics")
    if isinstance(raw_metrics, dict):
        for key, value in raw_metrics.items():
            item = _sanitize_metric_item(value)
            if item is not None:
                metrics[str(key)] = item

    return {
        "report_type": "device_health_report",
        "device_mac": sanitize_text(payload.get("device_mac")),
        "subject_name": sanitize_text(payload.get("subject_name")) or None,
        "device_name": sanitize_text(payload.get("device_name")) or None,
        "generated_at": sanitize_text(payload.get("generated_at")),
        "period": {
            "start_at": sanitize_text(period.get("start_at")),
            "end_at": sanitize_text(period.get("end_at")),
            "duration_minutes": _sanitize_int(period.get("duration_minutes")) or 0,
            "sample_count": _sanitize_int(period.get("sample_count")) or 0,
        },
        "summary": summary,
        "risk_level": sanitize_text(payload.get("risk_level")) or "unknown",
        "risk_flags": risk_flags,
        "key_findings": key_findings,
        "recommendations": recommendations,
        "metrics": metrics,
        "references": references,
    }
