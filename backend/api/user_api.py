from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException

from backend.dependencies import get_user_service, require_write_session_user
from backend.models.user_register_model import CommunityRegisterRequest, ElderRegisterRequest, FamilyRegisterRequest, UserRegisterResponse


router = APIRouter(prefix="/users", tags=["users"])


def _require_writer(authorization: str | None) -> None:
    try:
        require_write_session_user(authorization)
    except ValueError as exc:
        code = str(exc)
        if code in {"AUTH_REQUIRED", "INVALID_SESSION"}:
            raise HTTPException(status_code=401, detail=code) from exc
        raise HTTPException(status_code=403, detail=code) from exc


@router.post("/elders/register", response_model=UserRegisterResponse)
async def register_elder(payload: ElderRegisterRequest, authorization: str | None = Header(default=None)) -> UserRegisterResponse:
    _require_writer(authorization)
    try:
        return get_user_service().register_elder(payload)
    except ValueError as exc:
        if str(exc) == "PHONE_ALREADY_EXISTS":
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/families/register", response_model=UserRegisterResponse)
async def register_family(payload: FamilyRegisterRequest, authorization: str | None = Header(default=None)) -> UserRegisterResponse:
    _require_writer(authorization)
    try:
        return get_user_service().register_family(payload)
    except ValueError as exc:
        if str(exc) in {"PHONE_ALREADY_EXISTS", "LOGIN_USERNAME_ALREADY_EXISTS"}:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/community-staff/register", response_model=UserRegisterResponse)
async def register_community_staff(
    payload: CommunityRegisterRequest,
    authorization: str | None = Header(default=None),
) -> UserRegisterResponse:
    _require_writer(authorization)
    try:
        return get_user_service().register_community(payload)
    except ValueError as exc:
        if str(exc) in {"PHONE_ALREADY_EXISTS", "LOGIN_USERNAME_ALREADY_EXISTS"}:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        raise HTTPException(status_code=400, detail=str(exc)) from exc
