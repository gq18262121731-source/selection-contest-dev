"""Care Companion Agent V1.0.

This package is intentionally isolated from the health-analysis agent and from
the Go2 execution gateway. V1.0 produces advisory, non-executed action plans.
"""

from agent.robot_companion.robot_agent import RobotCompanionAgentService

__all__ = ["RobotCompanionAgentService"]
