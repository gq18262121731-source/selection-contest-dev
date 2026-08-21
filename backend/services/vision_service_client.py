from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import Any

import requests


@dataclass(frozen=True)
class VisionServiceEndpointResult:
    ok: bool
    status: str
    reason: str | None
    endpoint: str
    method: str
    url: str
    camera_id: str | None
    status_code: int | None
    elapsed_ms: int
    data: Any = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "status": self.status,
            "reason": self.reason,
            "endpoint": self.endpoint,
            "method": self.method,
            "url": self.url,
            "camera_id": self.camera_id,
            "status_code": self.status_code,
            "elapsed_ms": self.elapsed_ms,
            "data": self.data,
            "error": self.error,
        }


class VisionServiceClient:
    """Read-only client for an external Vision Service."""

    def __init__(
        self,
        *,
        base_url: str,
        default_camera_id: str = "camera_01",
        timeout: float = 2.5,
        session: requests.Session | None = None,
    ) -> None:
        self._base_url = self._normalize_base_url(base_url)
        self._default_camera_id = (default_camera_id or "camera_01").strip() or "camera_01"
        self._timeout = max(0.1, float(timeout))
        self._session = session or requests.Session()
        self._owns_session = session is None

    @property
    def base_url(self) -> str:
        return self._base_url

    @property
    def default_camera_id(self) -> str:
        return self._default_camera_id

    @property
    def timeout(self) -> float:
        return self._timeout

    def close(self) -> None:
        if self._owns_session:
            self._session.close()

    def get_health(self) -> dict[str, Any]:
        return self._get("/healthz").to_dict()

    def get_status(self, camera_id: str | None = None) -> dict[str, Any]:
        resolved_camera_id = self._resolve_camera_id(camera_id)
        return self._get("/status", params={"camera_id": resolved_camera_id}, camera_id=resolved_camera_id).to_dict()

    def get_stream_source(self, camera_id: str | None = None) -> dict[str, Any]:
        resolved_camera_id = self._resolve_camera_id(camera_id)
        return self._get(
            "/stream/source",
            params={"camera_id": resolved_camera_id},
            camera_id=resolved_camera_id,
        ).to_dict()

    def get_latest_result(self, camera_id: str | None = None) -> dict[str, Any]:
        resolved_camera_id = self._resolve_camera_id(camera_id)
        return self._get(
            f"/integration/results/{resolved_camera_id}/latest",
            camera_id=resolved_camera_id,
        ).to_dict()

    def probe(self, camera_id: str | None = None) -> dict[str, Any]:
        resolved_camera_id = self._resolve_camera_id(camera_id)
        health = self.get_health()
        status = self.get_status(resolved_camera_id)
        source = self.get_stream_source(resolved_camera_id)
        latest = self.get_latest_result(resolved_camera_id)
        overall_status = self._combine_statuses(health["status"], status["status"], source["status"], latest["status"])
        return {
            "base_url": self._base_url,
            "camera_id": resolved_camera_id,
            "timeout": self._timeout,
            "status": overall_status,
            "health": health,
            "service_status": status,
            "stream_source": source,
            "latest_result": latest,
        }

    def _get(
        self,
        endpoint: str,
        *,
        params: dict[str, Any] | None = None,
        camera_id: str | None = None,
    ) -> VisionServiceEndpointResult:
        url = f"{self._base_url}{endpoint}"
        started = perf_counter()

        try:
            response = self._session.get(
                url,
                params=params,
                timeout=self._timeout,
                headers={"Cache-Control": "no-store"},
            )
        except requests.exceptions.Timeout as exc:
            return self._result(
                ok=False,
                status="unavailable",
                reason="timeout",
                endpoint=endpoint,
                url=url,
                camera_id=camera_id,
                elapsed_ms=self._elapsed_ms(started),
                error=str(exc),
            )
        except requests.exceptions.ConnectionError as exc:
            return self._result(
                ok=False,
                status="unavailable",
                reason="connection_error",
                endpoint=endpoint,
                url=url,
                camera_id=camera_id,
                elapsed_ms=self._elapsed_ms(started),
                error=str(exc),
            )
        except requests.exceptions.RequestException as exc:
            return self._result(
                ok=False,
                status="unavailable",
                reason="request_error",
                endpoint=endpoint,
                url=url,
                camera_id=camera_id,
                elapsed_ms=self._elapsed_ms(started),
                error=str(exc),
            )

        elapsed_ms = self._elapsed_ms(started)
        if not response.ok:
            return self._result(
                ok=False,
                status="degraded",
                reason="http_error",
                endpoint=endpoint,
                url=response.url,
                camera_id=camera_id,
                status_code=response.status_code,
                elapsed_ms=elapsed_ms,
                data=self._safe_body(response),
                error=f"HTTP {response.status_code}",
            )

        body, parse_error = self._parse_body(response)
        if parse_error is not None:
            return self._result(
                ok=False,
                status="degraded",
                reason="invalid_response",
                endpoint=endpoint,
                url=response.url,
                camera_id=camera_id,
                status_code=response.status_code,
                elapsed_ms=elapsed_ms,
                data=self._safe_body(response),
                error=parse_error,
            )

        return self._result(
            ok=True,
            status="ok",
            reason=None,
            endpoint=endpoint,
            url=response.url,
            camera_id=camera_id,
            status_code=response.status_code,
            elapsed_ms=elapsed_ms,
            data=body,
        )

    def _parse_body(self, response: requests.Response) -> tuple[Any, str | None]:
        content_type = str(response.headers.get("Content-Type") or "").lower()
        text = response.text
        if "application/json" in content_type:
            try:
                return response.json(), None
            except ValueError as exc:
                return None, f"INVALID_JSON: {exc}"

        stripped = text.lstrip()
        if stripped.startswith("{") or stripped.startswith("["):
            try:
                return response.json(), None
            except ValueError as exc:
                return None, f"INVALID_JSON: {exc}"

        return {"text": text}, None

    @staticmethod
    def _safe_body(response: requests.Response) -> dict[str, Any]:
        text = response.text
        if len(text) > 500:
            text = f"{text[:500]}..."
        return {"text": text}

    def _result(
        self,
        *,
        ok: bool,
        status: str,
        reason: str | None,
        endpoint: str,
        url: str,
        camera_id: str | None,
        elapsed_ms: int,
        status_code: int | None = None,
        data: Any = None,
        error: str | None = None,
    ) -> VisionServiceEndpointResult:
        return VisionServiceEndpointResult(
            ok=ok,
            status=status,
            reason=reason,
            endpoint=endpoint,
            method="GET",
            url=str(url),
            camera_id=camera_id,
            status_code=status_code,
            elapsed_ms=elapsed_ms,
            data=data,
            error=error,
        )

    def _resolve_camera_id(self, camera_id: str | None) -> str:
        return (camera_id or self._default_camera_id).strip() or self._default_camera_id

    @staticmethod
    def _combine_statuses(*statuses: str) -> str:
        if any(status == "unavailable" for status in statuses):
            return "unavailable"
        if any(status == "degraded" for status in statuses):
            return "degraded"
        return "ok"

    @staticmethod
    def _elapsed_ms(started: float) -> int:
        return int((perf_counter() - started) * 1000)

    @staticmethod
    def _normalize_base_url(base_url: str) -> str:
        normalized = str(base_url or "").strip().rstrip("/")
        if not normalized:
            raise ValueError("VISION_SERVICE_BASE_URL_REQUIRED")
        return normalized
