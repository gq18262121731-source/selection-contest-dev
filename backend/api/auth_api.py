from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException

from backend.dependencies import get_care_service, get_user_service
from backend.models.auth_model import AuthAccountPreview, LoginRequest, LoginResponse, SessionUser
from backend.models.user_register_model import (
    CommunityRegisterRequest,
    ElderRegisterRequest,
    FamilyRegisterRequest,
    UserRegisterResponse,
)


router = APIRouter(prefix="/auth", tags=["auth"])


def _extract_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return token.strip()


def _raise_registration_error(exc: ValueError) -> None:
    code = str(exc)
    if code in {"PHONE_ALREADY_EXISTS", "LOGIN_USERNAME_ALREADY_EXISTS"}:
        raise HTTPException(status_code=409, detail=code) from exc
    raise HTTPException(status_code=400, detail=code) from exc


@router.get("/mock-accounts", response_model=list[AuthAccountPreview])
async def list_mock_accounts() -> list[AuthAccountPreview]:
    return get_care_service().list_auth_accounts()


@router.post("/login", response_model=LoginResponse)
async def login(payload: LoginRequest) -> LoginResponse:
    result = get_care_service().login(payload.username, payload.password)
    if not result:
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    return result


@router.post("/mock-login", response_model=LoginResponse)
async def mock_login(payload: LoginRequest) -> LoginResponse:
    result = get_care_service().login_demo(payload.username, payload.password)
    if not result:
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    return result


@router.post("/register/elder", response_model=UserRegisterResponse)
async def register_elder(payload: ElderRegisterRequest) -> UserRegisterResponse:
    try:
        return get_user_service().register_elder(payload)
    except ValueError as exc:
        _raise_registration_error(exc)


@router.post("/register/family", response_model=UserRegisterResponse)
async def register_family(payload: FamilyRegisterRequest) -> UserRegisterResponse:
    try:
        return get_user_service().register_family(payload)
    except ValueError as exc:
        _raise_registration_error(exc)


@router.post("/register/community-staff", response_model=UserRegisterResponse)
async def register_community_staff(payload: CommunityRegisterRequest) -> UserRegisterResponse:
    try:
        return get_user_service().register_community(payload)
    except ValueError as exc:
        _raise_registration_error(exc)


@router.get("/me", response_model=SessionUser)
async def me(authorization: str | None = Header(default=None)) -> SessionUser:
    token = _extract_token(authorization)
    if not token:
        raise HTTPException(status_code=401, detail="缺少认证信息")
    user = get_care_service().resolve_session(token)
    if not user:
        raise HTTPException(status_code=401, detail="登录状态已失效")
    return user
