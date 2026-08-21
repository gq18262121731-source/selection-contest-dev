from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException

from backend.dependencies import get_relation_service, require_write_session_user
from backend.models.relation_model import FamilyRelationCreateRequest, FamilyRelationRecord


router = APIRouter(prefix="/relations", tags=["relations"])


def _require_writer(authorization: str | None) -> None:
    try:
        require_write_session_user(authorization)
    except ValueError as exc:
        code = str(exc)
        if code in {"AUTH_REQUIRED", "INVALID_SESSION"}:
            raise HTTPException(status_code=401, detail=code) from exc
        raise HTTPException(status_code=403, detail=code) from exc


@router.post("/family-bind", response_model=FamilyRelationRecord)
async def bind_family_to_elder(
    payload: FamilyRelationCreateRequest,
    authorization: str | None = Header(default=None),
) -> FamilyRelationRecord:
    _require_writer(authorization)
    try:
        return get_relation_service().bind_family_to_elder(payload)
    except ValueError as exc:
        code = str(exc)
        if code == "RELATION_ALREADY_EXISTS":
            raise HTTPException(status_code=409, detail=code) from exc
        if code == "USER_NOT_FOUND":
            raise HTTPException(status_code=404, detail=code) from exc
        raise HTTPException(status_code=400, detail=code) from exc
