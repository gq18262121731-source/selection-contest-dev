from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException

from agent.robot_companion.context_manager import RobotCompanionContextError
from agent.robot_companion.robot_agent import RobotCompanionAgentService
from backend.dependencies import get_robot_companion_service
from backend.schemas.robot_companion_schema import (
    RobotCompanionDialogueRequest,
    RobotCompanionDialogueResponse,
)


router = APIRouter(prefix="/robot-agent", tags=["robot-companion-agent"])


@router.post("/dialogue", response_model=RobotCompanionDialogueResponse)
async def robot_companion_dialogue(
    payload: RobotCompanionDialogueRequest,
    service: RobotCompanionAgentService = Depends(get_robot_companion_service),
) -> RobotCompanionDialogueResponse:
    try:
        return await asyncio.to_thread(service.dialogue, payload)
    except RobotCompanionContextError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": exc.message},
        ) from exc
