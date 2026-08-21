from __future__ import annotations

from backend.schemas.robot_companion_schema import (
    RobotCompanionActionPlan,
    RobotCompanionActionType,
    RobotCompanionContext,
    RobotCompanionDecision,
    RobotCompanionIntent,
)


class RobotCompanionActionPlanner:
    """Maps fixed intents to an allow-listed, non-executable V1.0 plan."""

    def plan(
        self,
        *,
        decision: RobotCompanionDecision,
        text: str,
        context: RobotCompanionContext,
    ) -> RobotCompanionActionPlan:
        del context
        if decision.intent == RobotCompanionIntent.WALK_REQUEST:
            return RobotCompanionActionPlan(
                type=RobotCompanionActionType.PREPARE_FOLLOW,
                parameters={
                    "duration_seconds": 1800,
                    "distance_limit_meters": 5,
                },
            )
        if decision.intent == RobotCompanionIntent.EMERGENCY:
            action = (
                RobotCompanionActionType.CALL_FAMILY
                if any(keyword in text for keyword in ("家属", "家人", "儿子", "女儿"))
                else RobotCompanionActionType.REQUEST_HELP
            )
            return RobotCompanionActionPlan(type=action)
        return RobotCompanionActionPlan(type=RobotCompanionActionType.NONE)
