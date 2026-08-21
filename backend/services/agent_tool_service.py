from __future__ import annotations

from typing import Any, TypedDict

from backend.schemas.agent import HealthExplainRequest
from backend.schemas.health import HealthScoreRequest, VitalSignsPayload
from backend.schemas.warning import WarningCheckRequest, WarningWindowPoint
from backend.services.explanation_service import ExplanationService
from backend.services.health_score_service import HealthScoreService
from backend.services.warning_service import WarningService


class HealthAgentToolService:
    """Structured local tools for future LangChain and LangGraph agents."""

    def __init__(
        self,
        *,
        health_score_service: HealthScoreService,
        warning_service: WarningService,
        explanation_service: ExplanationService,
    ) -> None:
        self.health_score_service = health_score_service
        self.warning_service = warning_service
        self.explanation_service = explanation_service

    def get_health_score_tool(self, payload: dict[str, Any]) -> dict[str, Any]:
        request = HealthScoreRequest(**payload)
        return self.health_score_service.score(request).model_dump(mode="json")

    def check_warning_tool(self, payload: dict[str, Any]) -> dict[str, Any]:
        if payload.get("current_data") is not None:
            request = WarningCheckRequest(current_data=VitalSignsPayload(**payload["current_data"]))
        else:
            request = WarningCheckRequest(window_data=[WarningWindowPoint(**item) for item in payload.get("window_data", [])])
        return self.warning_service.check(request).model_dump(mode="json")

    def explain_health_result_tool(self, payload: dict[str, Any]) -> dict[str, Any]:
        request = HealthExplainRequest(**payload)
        return self.explanation_service.explain(request).model_dump(mode="json")

    def build_langchain_tools(self) -> list[Any]:
        """Build LangChain v1 style tools."""

        from langchain_core.tools import StructuredTool

        return [
            StructuredTool.from_function(
                func=self.get_health_score_tool,
                name="get_health_score_tool",
                description="Score a single elderly health snapshot and return structured risk output.",
            ),
            StructuredTool.from_function(
                func=self.check_warning_tool,
                name="check_warning_tool",
                description="Check warning level for a single point or an aggregated monitoring window.",
            ),
            StructuredTool.from_function(
                func=self.explain_health_result_tool,
                name="explain_health_result_tool",
                description="Generate a role-aware explanation for a structured health score result.",
            ),
        ]

    def build_langgraph_workflow(self) -> Any:
        """Build a minimal LangGraph workflow placeholder for future orchestration."""

        from langgraph.graph import END, StateGraph

        class HealthAgentState(TypedDict, total=False):
            payload: dict[str, Any]
            score_result: dict[str, Any]
            warning_result: dict[str, Any]
            explanation_result: dict[str, Any]

        graph = StateGraph(HealthAgentState)

        def score_node(state: HealthAgentState) -> HealthAgentState:
            payload = state.get("payload", {})
            if {"elderly_id", "device_id", "timestamp"} <= set(payload):
                return {"score_result": self.get_health_score_tool(payload)}
            return {}

        def warning_node(state: HealthAgentState) -> HealthAgentState:
            payload = state.get("payload", {})
            if payload:
                return {"warning_result": self.check_warning_tool(payload)}
            return {}

        graph.add_node("score", score_node)
        graph.add_node("warning", warning_node)
        graph.set_entry_point("score")
        graph.add_edge("score", "warning")
        graph.add_edge("warning", END)
        return graph.compile()
