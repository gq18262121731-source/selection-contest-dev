from __future__ import annotations

from backend.schemas.robot_companion_schema import (
    RobotCompanionActionPlan,
    RobotCompanionActionType,
    RobotCompanionContext,
    RobotCompanionSafetyDecision,
)


class RobotCompanionSafetyGuard:
    """Deterministic V1.0 guard. It never enables or executes an action."""

    def evaluate(
        self,
        *,
        context: RobotCompanionContext,
        plan: RobotCompanionActionPlan,
    ) -> RobotCompanionSafetyDecision:
        if plan.type in {RobotCompanionActionType.NONE, RobotCompanionActionType.SUGGEST_WALK}:
            return RobotCompanionSafetyDecision(
                status="allowed",
                code="ADVISORY_ONLY",
                reason="当前计划仅包含语言建议，不触发机器人或外部系统。",
            )

        if plan.type in {
            RobotCompanionActionType.CALL_FAMILY,
            RobotCompanionActionType.REQUEST_HELP,
        }:
            return RobotCompanionSafetyDecision(
                status="blocked",
                code="HUMAN_CONFIRMATION_REQUIRED",
                reason="V1.0 只生成求助建议，联系家属或社区必须由人工确认。",
            )

        health = context.health
        environment = context.environment
        if health.sos:
            return self._blocked("SOS_ACTIVE", "检测到 SOS 状态，不能生成普通陪伴运动。")
        if health.recent_fall:
            return self._blocked("RECENT_FALL", "最近存在跌倒事件，暂不建议启动陪伴运动。")
        if health.risk_level == "high":
            return self._blocked("HEALTH_RISK_HIGH", "当前健康风险较高，暂不建议启动陪伴运动。")
        if health.data_freshness == "missing":
            return self._blocked("HEALTH_DATA_MISSING", "缺少有效健康数据，无法确认活动安全性。")
        if health.data_freshness == "stale":
            return self._blocked("HEALTH_DATA_STALE", "健康数据已过期，请先复测再安排活动。")
        if environment.weather == "rain":
            return self._blocked("WEATHER_RAIN", "当前有雨，路面湿滑，不建议启动户外陪伴运动。")
        if environment.weather == "windy" or (environment.wind_level or 0) >= 5:
            return self._blocked("WEATHER_STRONG_WIND", "当前风力较大，不建议启动户外陪伴运动。")
        if environment.weather == "hot" or (environment.temperature or 0) >= 35:
            return self._blocked("WEATHER_HIGH_TEMPERATURE", "当前天气炎热，不建议启动户外陪伴运动。")
        if environment.weather == "cold" or (
            environment.temperature is not None and environment.temperature <= 5
        ):
            return self._blocked("WEATHER_LOW_TEMPERATURE", "当前气温较低，不建议启动户外陪伴运动。")
        if not context.location.city or not context.location.area:
            return self._blocked("LOCATION_UNAVAILABLE", "当前位置不可用，不能准备陪伴运动计划。")
        if not context.robot.online:
            return self._blocked("ROBOT_OFFLINE", "机器人当前不在线，不能准备陪伴运动计划。")
        if not context.robot.motion_enabled:
            return self._blocked("MOTION_DISABLED", "真实运动模式未开启，当前只展示动作计划。")
        return self._blocked("EXECUTION_DISABLED", "V1.0 不允许执行任何机器人动作。")

    @staticmethod
    def _blocked(code: str, reason: str) -> RobotCompanionSafetyDecision:
        return RobotCompanionSafetyDecision(status="blocked", code=code, reason=reason)
