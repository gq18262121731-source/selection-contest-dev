from __future__ import annotations

from typing import Protocol

from backend.schemas.robot_companion_schema import (
    RobotCompanionEnvironmentContext,
    RobotCompanionLocationContext,
    RobotCompanionRobotContext,
)


class WeatherProvider(Protocol):
    def get_weather(
        self,
        *,
        location: RobotCompanionLocationContext,
        scenario: str,
    ) -> RobotCompanionEnvironmentContext: ...


class LocationProvider(Protocol):
    def get_location(
        self,
        *,
        elder_id: str,
        location_hint: str | None,
        elder_apartment: str,
    ) -> RobotCompanionLocationContext: ...


class RobotStateProvider(Protocol):
    def get_state(self) -> RobotCompanionRobotContext: ...


class MockLocationProvider:
    def __init__(self, *, city: str = "南京", default_area: str = "住宅附近") -> None:
        self._city = city
        self._default_area = default_area

    def get_location(
        self,
        *,
        elder_id: str,
        location_hint: str | None,
        elder_apartment: str,
    ) -> RobotCompanionLocationContext:
        del elder_id
        area = location_hint or elder_apartment or self._default_area
        return RobotCompanionLocationContext(
            city=self._city,
            area=area,
            address=area,
        )


class MockWeatherProvider:
    _SCENARIOS = {
        "sunny": {
            "description": "晴",
            "temperature": 22.0,
            "humidity": 50,
            "wind_level": 2,
            "suggestion": "天气晴朗，温度舒适，适合适量活动。",
        },
        "rain": {
            "description": "小雨",
            "temperature": 18.0,
            "humidity": 85,
            "wind_level": 3,
            "suggestion": "当前有雨，外出请携带雨具并注意路面湿滑。",
        },
        "windy": {
            "description": "大风",
            "temperature": 16.0,
            "humidity": 45,
            "wind_level": 6,
            "suggestion": "当前风力较大，建议减少户外活动。",
        },
        "hot": {
            "description": "晴热",
            "temperature": 35.0,
            "humidity": 55,
            "wind_level": 2,
            "suggestion": "当前天气炎热，建议避免长时间户外暴露并注意补水。",
        },
        "cold": {
            "description": "低温",
            "temperature": 3.0,
            "humidity": 60,
            "wind_level": 3,
            "suggestion": "当前气温较低，外出请增加衣物并缩短活动时间。",
        },
    }

    def get_weather(
        self,
        *,
        location: RobotCompanionLocationContext,
        scenario: str,
    ) -> RobotCompanionEnvironmentContext:
        del location
        weather = scenario if scenario in self._SCENARIOS else "sunny"
        return RobotCompanionEnvironmentContext(
            weather=weather,
            **self._SCENARIOS[weather],
        )


class MockRobotStateProvider:
    """V1.0 exposes robot presence while keeping motion permanently disabled."""

    def get_state(self) -> RobotCompanionRobotContext:
        return RobotCompanionRobotContext(online=True, motion_enabled=False)
