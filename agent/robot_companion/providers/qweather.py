from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import urlparse

import requests

from agent.robot_companion.tool_registry import MockWeatherProvider, WeatherProvider
from backend.schemas.robot_companion_schema import (
    RobotCompanionEnvironmentContext,
    RobotCompanionLocationContext,
)


logger = logging.getLogger(__name__)


class QWeatherProviderError(RuntimeError):
    pass


class QWeatherProvider:
    """QWeather v7 current-weather provider with deterministic Mock fallback."""

    CURRENT_WEATHER_PATH = "/v7/weather/now"
    _PRECIPITATION_TERMS = ("雨", "雪", "冰雹", "雷暴", "冻雨")
    _CLEAR_TERMS = ("晴", "多云", "阴")

    def __init__(
        self,
        *,
        api_key: str,
        api_host: str,
        location_code: str,
        timeout_seconds: float = 3.0,
        session: requests.Session | None = None,
        fallback: WeatherProvider | None = None,
    ) -> None:
        self._api_key = api_key.strip()
        if not self._api_key:
            raise ValueError("QWEATHER_API_KEY is required")
        self._api_host = self._normalize_api_host(api_host)
        self._location_code = self._normalize_location(location_code)
        self._timeout_seconds = max(0.5, min(10.0, float(timeout_seconds)))
        self._session = session or requests.Session()
        self._fallback = fallback or MockWeatherProvider()

    def get_weather(
        self,
        *,
        location: RobotCompanionLocationContext,
        scenario: str,
    ) -> RobotCompanionEnvironmentContext:
        try:
            response = self._session.get(
                f"{self._api_host}{self.CURRENT_WEATHER_PATH}",
                params={
                    "location": self._location_code,
                    "lang": "zh",
                },
                headers={
                    "Accept": "application/json",
                    "Accept-Encoding": "gzip",
                    "X-QW-Api-Key": self._api_key,
                },
                timeout=self._timeout_seconds,
            )
            if not response.ok:
                raise QWeatherProviderError(f"QWeather HTTP status {response.status_code}")
            payload = response.json()
            return self.normalize(payload)
        except (requests.RequestException, ValueError, TypeError, QWeatherProviderError) as exc:
            logger.warning("QWeather unavailable; using Mock weather fallback: %s", exc)
            return self._fallback.get_weather(location=location, scenario=scenario)

    @classmethod
    def normalize(cls, payload: dict[str, Any]) -> RobotCompanionEnvironmentContext:
        if str(payload.get("code", "")) != "200":
            raise QWeatherProviderError(
                f"QWeather response code {str(payload.get('code') or 'missing')}"
            )
        now = payload.get("now")
        if not isinstance(now, dict):
            raise QWeatherProviderError("QWeather response is missing now")

        description = str(now.get("text") or "").strip()
        if not description:
            raise QWeatherProviderError("QWeather response is missing weather text")
        temperature = cls._number(now.get("temp"), field="temp")
        humidity = cls._bounded_int(now.get("humidity"), field="humidity", minimum=0, maximum=100)
        wind_level = cls._wind_level(now.get("windScale"))
        weather = cls._weather_category(
            description=description,
            temperature=temperature,
            wind_level=wind_level,
        )
        return RobotCompanionEnvironmentContext(
            weather=weather,
            temperature=temperature,
            humidity=humidity,
            wind_level=wind_level,
            description=description,
            suggestion=cls._suggestion(
                weather=weather,
                description=description,
            ),
            provider="qweather",
            source="qweather",
        )

    @classmethod
    def _weather_category(
        cls,
        *,
        description: str,
        temperature: float,
        wind_level: int,
    ) -> str:
        if any(term in description for term in cls._PRECIPITATION_TERMS):
            return "rain"
        if wind_level >= 5 or "大风" in description or "沙尘" in description:
            return "windy"
        if temperature >= 35:
            return "hot"
        if temperature <= 5:
            return "cold"
        if any(term in description for term in cls._CLEAR_TERMS):
            return "sunny"
        return "unknown"

    @staticmethod
    def _suggestion(*, weather: str, description: str) -> str:
        if weather == "rain":
            return f"当前天气为{description}，外出请携带雨具并注意路面湿滑。"
        if weather == "windy":
            return f"当前天气为{description}且风力较大，建议减少户外活动。"
        if weather == "hot":
            return f"当前天气为{description}且气温较高，建议避免长时间户外暴露并注意补水。"
        if weather == "cold":
            return f"当前天气为{description}且气温较低，外出请增加衣物并缩短活动时间。"
        if weather == "sunny":
            return f"当前天气为{description}，风力不大，适合结合健康状态安排适量活动。"
        return f"当前天气为{description}，请结合现场情况谨慎安排活动。"

    @staticmethod
    def _normalize_api_host(value: str) -> str:
        raw = value.strip()
        if not raw:
            raise ValueError("QWEATHER_API_HOST is required")
        parsed = urlparse(raw if "://" in raw else f"https://{raw}")
        hostname = (parsed.hostname or "").lower()
        if (
            parsed.scheme != "https"
            or not hostname.endswith(".qweatherapi.com")
            or parsed.port is not None
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("QWEATHER_API_HOST must be an HTTPS *.qweatherapi.com host")
        return f"https://{hostname}"

    @staticmethod
    def _normalize_location(value: str) -> str:
        raw = value.strip()
        if not raw:
            raise ValueError("QWEATHER_LOCATION is required")
        if raw.isdigit():
            return raw
        parts = [part.strip() for part in raw.split(",")]
        if len(parts) != 2:
            raise ValueError("QWEATHER_LOCATION must be a LocationID or longitude,latitude")
        try:
            longitude, latitude = (float(part) for part in parts)
        except ValueError as exc:
            raise ValueError(
                "QWEATHER_LOCATION must be a LocationID or longitude,latitude"
            ) from exc
        if not -180 <= longitude <= 180 or not -90 <= latitude <= 90:
            raise ValueError("QWEATHER_LOCATION coordinates are out of range")
        return f"{longitude:.2f},{latitude:.2f}"

    @staticmethod
    def _number(value: Any, *, field: str) -> float:
        try:
            return float(value)
        except (TypeError, ValueError) as exc:
            raise QWeatherProviderError(f"QWeather response has invalid {field}") from exc

    @staticmethod
    def _bounded_int(
        value: Any,
        *,
        field: str,
        minimum: int,
        maximum: int,
    ) -> int:
        try:
            result = int(float(value))
        except (TypeError, ValueError) as exc:
            raise QWeatherProviderError(f"QWeather response has invalid {field}") from exc
        if not minimum <= result <= maximum:
            raise QWeatherProviderError(f"QWeather response has out-of-range {field}")
        return result

    @staticmethod
    def _wind_level(value: Any) -> int:
        levels = [int(item) for item in re.findall(r"\d+", str(value or ""))]
        if not levels:
            raise QWeatherProviderError("QWeather response has invalid windScale")
        return max(0, min(12, max(levels)))
