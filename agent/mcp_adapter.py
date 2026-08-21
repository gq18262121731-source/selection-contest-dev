from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass(slots=True)
class ToolInvocation:
    name: str
    request_id: str = ""
    operator_role: str = ""
    community_id: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)

    @property
    def arguments(self) -> dict[str, Any]:
        return self.payload


@dataclass(slots=True)
class ToolInvocationResult:
    name: str
    status: str
    source: str
    success: bool
    data: dict[str, Any] = field(default_factory=dict)
    error_code: str | None = None
    error_message: str | None = None
    error: str | None = None


@dataclass(slots=True)
class MCPToolSpec:
    name: str
    description: str
    source: str = "local_service"


class ToolAdapter:
    def list_tools(self) -> list[MCPToolSpec]:
        raise NotImplementedError

    def invoke_many(self, calls: list[ToolInvocation]) -> list[ToolInvocationResult]:
        raise NotImplementedError


class LocalToolAdapter(ToolAdapter):
    """Future MCP boundary backed by current in-process services."""

    def __init__(self) -> None:
        self._tools: dict[str, tuple[MCPToolSpec, Callable[..., dict[str, Any]]]] = {}

    def register_tool(
        self,
        *,
        name: str,
        description: str,
        handler: Callable[..., dict[str, Any]],
        source: str = "local_service",
    ) -> None:
        self._tools[name] = (MCPToolSpec(name=name, description=description, source=source), handler)

    def list_tools(self) -> list[MCPToolSpec]:
        return [spec for spec, _handler in self._tools.values()]

    def invoke_many(self, calls: list[ToolInvocation]) -> list[ToolInvocationResult]:
        results: list[ToolInvocationResult] = []
        for call in calls:
            spec_handler = self._tools.get(call.name)
            if spec_handler is None:
                results.append(
                    ToolInvocationResult(
                        name=call.name,
                        status="missing",
                        success=False,
                        source="local_service",
                        error_code="tool_not_registered",
                        error_message="Tool is not registered",
                        error="tool_not_registered",
                    )
                )
                continue
            spec, handler = spec_handler
            try:
                data = handler(call)
                results.append(
                    ToolInvocationResult(
                        name=call.name,
                        status="ok",
                        success=True,
                        source=spec.source,
                        data=data,
                    )
                )
            except Exception as exc:
                results.append(
                    ToolInvocationResult(
                        name=call.name,
                        status="error",
                        success=False,
                        source=spec.source,
                        error_code=exc.__class__.__name__,
                        error_message=str(exc),
                        error=exc.__class__.__name__,
                    )
                )
        return results


class ReservedMCPToolAdapter(ToolAdapter):
    """Reserved adapter for future MCP transport integration."""

    def __init__(self, tool_specs: list[MCPToolSpec] | None = None) -> None:
        self._tool_specs = tool_specs or []

    def list_tools(self) -> list[MCPToolSpec]:
        return list(self._tool_specs)

    def invoke_many(self, calls: list[ToolInvocation]) -> list[ToolInvocationResult]:
        return [
            ToolInvocationResult(
                name=call.name,
                status="reserved",
                success=False,
                source="mcp_reserved",
                error_code="mcp_not_connected",
                error_message="MCP transport is not connected",
                error="mcp_not_connected",
            )
            for call in calls
        ]
