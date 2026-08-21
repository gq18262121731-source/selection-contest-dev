from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    """Standard error payload for API failures."""

    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


def build_success_response(data: BaseModel | dict[str, Any]) -> dict[str, Any]:
    """Build a standard success envelope."""

    if isinstance(data, BaseModel):
        payload = data.model_dump(mode="json")
    else:
        payload = data
    return {
        "code": "OK",
        "message": "success",
        "data": payload,
    }


def build_error_response(code: str, message: str, details: dict[str, Any] | None = None) -> ErrorResponse:
    """Build a standard error envelope."""

    return ErrorResponse(code=code, message=message, details=details or {})
