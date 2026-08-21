from __future__ import annotations

from typing import Any

import pytest

from agent.robot_companion.providers.qweather import QWeatherProvider
from backend.config import Settings
from backend.schemas.robot_companion_schema import RobotCompanionLocationContext


class _FakeResponse:
    def __init__(
        self,
        payload: dict[str, Any],
        *,
        ok: bool = True,
        status_code: int = 200,
    ) -> None:
        self._payload = payload
        self.ok = ok
        self.status_code = status_code

    def json(self) -> dict[str, Any]:
        return self._payload


class _FakeSession:
    def __init__(self, response: _FakeResponse) -> None:
        self._response = response
        self.calls: list[dict[str, Any]] = []

    def get(self, url: str, **kwargs: Any) -> _FakeResponse:
        self.calls.append({"url": url, **kwargs})
        return self._response


def _location() -> RobotCompanionLocationContext:
    return RobotCompanionLocationContext(
        city="南京",
        area="住宅附近",
        address="住宅附近",
    )


def _payload(*, text: str = "小雨", temp: str = "18", wind_scale: str = "5") -> dict[str, Any]:
    return {
        "code": "200",
        "updateTime": "2026-07-29T15:00+08:00",
        "now": {
            "text": text,
            "temp": temp,
            "windScale": wind_scale,
            "humidity": "80",
        },
    }


def test_qweather_normalizes_current_weather_for_safety_contract() -> None:
    result = QWeatherProvider.normalize(_payload())

    assert result.weather == "rain"
    assert result.temperature == 18
    assert result.wind_level == 5
    assert result.humidity == 80
    assert result.description == "小雨"
    assert result.provider == "qweather"
    assert result.source == "qweather"


def test_qweather_uses_private_host_header_auth_and_normalized_coordinates() -> None:
    session = _FakeSession(_FakeResponse(_payload(text="晴", temp="22", wind_scale="2")))
    provider = QWeatherProvider(
        api_key="test-key",
        api_host="abc123.qweatherapi.com",
        location_code="118.796877,32.060255",
        session=session,  # type: ignore[arg-type]
    )

    result = provider.get_weather(
        location=_location(),
        scenario="rain",
    )

    assert result.weather == "sunny"
    assert result.provider == "qweather"
    assert session.calls == [
        {
            "url": "https://abc123.qweatherapi.com/v7/weather/now",
            "params": {"location": "118.80,32.06", "lang": "zh"},
            "headers": {
                "Accept": "application/json",
                "Accept-Encoding": "gzip",
                "X-QW-Api-Key": "test-key",
            },
            "timeout": 3.0,
        }
    ]


def test_qweather_failure_degrades_to_requested_mock_scenario() -> None:
    session = _FakeSession(
        _FakeResponse({"code": "401"}, ok=False, status_code=401)
    )
    provider = QWeatherProvider(
        api_key="test-key",
        api_host="https://abc123.qweatherapi.com",
        location_code="101190101",
        session=session,  # type: ignore[arg-type]
    )

    result = provider.get_weather(
        location=_location(),
        scenario="windy",
    )

    assert result.weather == "windy"
    assert result.provider == "mock"
    assert result.source == "mock"


def test_qweather_rejects_retired_public_or_non_qweather_hosts() -> None:
    with pytest.raises(ValueError, match="QWEATHER_API_HOST"):
        QWeatherProvider(
            api_key="test-key",
            api_host="https://devapi.qweather.com",
            location_code="101190101",
        )

    with pytest.raises(ValueError, match="QWEATHER_API_HOST"):
        QWeatherProvider(
            api_key="test-key",
            api_host="http://metadata.internal",
            location_code="101190101",
        )


def test_weather_provider_configuration_defaults_to_mock() -> None:
    default_settings = Settings(_env_file=None)
    configured_settings = Settings(
        _env_file=None,
        weather_provider="qweather",
        qweather_api_key="test-key",
        qweather_api_host="abc123.qweatherapi.com",
        qweather_location="118.80,32.06",
    )

    assert default_settings.weather_provider == "mock"
    assert default_settings.qweather_configured is False
    assert configured_settings.qweather_configured is True
