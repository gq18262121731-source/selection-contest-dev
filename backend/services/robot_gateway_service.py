from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import requests

from backend.models.alarm_model import AlarmRecord
from backend.models.robot_model import RobotFallEventRequest, RobotTargetMoveRequest


@dataclass(frozen=True)
class RobotGatewayResult:
    ok: bool
    status: str
    base_url: str
    endpoint: str
    status_code: int | None = None
    data: Any = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "status": self.status,
            "base_url": self.base_url,
            "endpoint": self.endpoint,
            "status_code": self.status_code,
            "data": self.data,
            "error": self.error,
        }


class RobotGatewayService:
    """Client/proxy for the Go2 gateway.

    The main system owns event and alarm decisions; the Go2 gateway remains the
    embodied execution endpoint.
    """

    def __init__(
        self,
        *,
        base_url: str,
        timeout_seconds: float = 1.5,
        enabled: bool = True,
        session: requests.Session | None = None,
    ) -> None:
        self._base_url = self._normalize_base_url(base_url)
        self._timeout_seconds = max(0.1, float(timeout_seconds))
        self._enabled = bool(enabled)
        self._session = session or requests.Session()

    @property
    def base_url(self) -> str:
        return self._base_url

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def timeout_seconds(self) -> float:
        return self._timeout_seconds

    def status(self) -> dict[str, Any]:
        return self._get("/api/robot/status").to_dict()

    def health(self) -> dict[str, Any]:
        return self._get("/health").to_dict()

    def list_tasks(self) -> dict[str, Any]:
        return self._get("/api/robot/tasks").to_dict()

    def get_task(self, task_id: str) -> dict[str, Any]:
        return self._get(f"/api/robot/tasks/{task_id}").to_dict()

    def submit_target_move(self, payload: RobotTargetMoveRequest) -> dict[str, Any]:
        return self._post("/api/robot/tasks/target-move", payload.model_dump(mode="json")).to_dict()

    def submit_fall_event(self, payload: RobotFallEventRequest) -> dict[str, Any]:
        return self._post(
            "/api/robot/events/fall",
            payload.model_dump(mode="json", by_alias=False),
        ).to_dict()

    async def submit_fall_confirmation_async(
        self,
        *,
        event: dict[str, object],
        alarm: AlarmRecord,
        external_task_id: str | None = None,
        trace_id: str | None = None,
    ) -> dict[str, Any]:
        payload = self.build_fall_confirmation_payload(
            event=event,
            alarm=alarm,
            external_task_id=external_task_id,
            trace_id=trace_id,
        )
        return await asyncio.to_thread(self.submit_fall_event, payload)

    def build_fall_confirmation_payload(
        self,
        *,
        event: dict[str, object],
        alarm: AlarmRecord,
        external_task_id: str | None = None,
        trace_id: str | None = None,
    ) -> RobotFallEventRequest:
        event_metadata = dict(event.get("metadata") or {}) if isinstance(event.get("metadata"), dict) else {}
        metadata = dict(alarm.metadata or {})
        metadata.update(event_metadata)
        normalized_event = dict(metadata.get("event") or {}) if isinstance(metadata.get("event"), dict) else {}

        fall_score = self._first_number(
            normalized_event.get("fall_score"),
            normalized_event.get("fall_prob"),
            event.get("fall_score"),
            event.get("fall_prob"),
            alarm.anomaly_probability,
            default=0.0,
        )
        camera_id = str(
            normalized_event.get("camera_id")
            or event.get("camera_id")
            or metadata.get("camera_id")
            or ""
        ).strip() or None
        elder_id = str(
            metadata.get("elder_id")
            or normalized_event.get("elder_id")
            or event.get("elder_id")
            or ""
        ).strip()
        location = str(
            normalized_event.get("location")
            or event.get("location")
            or metadata.get("location")
            or camera_id
            or "unknown"
        ).strip() or "unknown"
        source_event_id = str(
            normalized_event.get("incident_id")
            or event.get("incident_id")
            or metadata.get("incident_id")
            or alarm.id
        ).strip()

        metadata_payload = {
            "alarm_id": alarm.id,
            "alarm_type": alarm.alarm_type.value,
            "camera_id": camera_id,
            "incident_id": source_event_id,
            "source_event_id": source_event_id,
            "external_task_id": external_task_id,
            "trace_id": trace_id,
            "snapshot_url": normalized_event.get("snapshot_url") or event.get("snapshot_url") or metadata.get("snapshot_url"),
            "source": event.get("source") or metadata.get("source") or "vision_service",
        }
        return RobotFallEventRequest(
            elder_id=elder_id,
            location=location,
            confidence=fall_score,
            source_event_id=source_event_id,
            external_task_id=external_task_id,
            trace_id=trace_id,
            camera_id=camera_id,
            metadata=metadata_payload,
        )

    def _get(self, endpoint: str) -> RobotGatewayResult:
        return self._request("GET", endpoint)

    def _post(self, endpoint: str, payload: dict[str, Any]) -> RobotGatewayResult:
        return self._request("POST", endpoint, json=payload)

    def _request(self, method: str, endpoint: str, **kwargs: Any) -> RobotGatewayResult:
        if not self._enabled:
            return RobotGatewayResult(False, "disabled", self._base_url, endpoint)

        url = f"{self._base_url}{endpoint}"
        try:
            response = self._session.request(method, url, timeout=self._timeout_seconds, **kwargs)
            data = self._parse_response(response)
            return RobotGatewayResult(
                ok=bool(response.ok),
                status="ok" if response.ok else "degraded",
                base_url=self._base_url,
                endpoint=endpoint,
                status_code=response.status_code,
                data=data,
                error=None if response.ok else f"HTTP {response.status_code}",
            )
        except requests.exceptions.Timeout as exc:
            return RobotGatewayResult(False, "unavailable", self._base_url, endpoint, error=f"timeout: {exc}")
        except requests.exceptions.ConnectionError as exc:
            return RobotGatewayResult(False, "unavailable", self._base_url, endpoint, error=f"connection_error: {exc}")
        except requests.exceptions.RequestException as exc:
            return RobotGatewayResult(False, "unavailable", self._base_url, endpoint, error=f"request_error: {exc}")

    @staticmethod
    def _parse_response(response: requests.Response) -> Any:
        content_type = str(response.headers.get("content-type") or "").lower()
        if "json" in content_type:
            try:
                return response.json()
            except ValueError:
                return {"text": response.text}
        text = response.text
        try:
            return response.json()
        except ValueError:
            return {"text": text}

    @staticmethod
    def _normalize_base_url(value: str) -> str:
        cleaned = str(value or "").strip().rstrip("/")
        return cleaned or "http://127.0.0.1:8090"

    @staticmethod
    def _first_number(*values: object, default: float = 0.0) -> float:
        for value in values:
            try:
                if value is not None:
                    return max(0.0, min(1.0, float(value)))
            except (TypeError, ValueError):
                continue
        return default
