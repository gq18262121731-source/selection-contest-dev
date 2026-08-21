from __future__ import annotations

import asyncio

import requests
from fastapi import APIRouter, Depends, HTTPException, Query, Response

from backend.dependencies import get_robot_gateway_service, get_robot_task_service, get_settings_dependency
from backend.models.robot_model import (
    RobotCallbackAck,
    RobotFallEventRequest,
    RobotTaskCancelResponse,
    RobotTaskDetailResponse,
    RobotTaskListResponse,
    RobotTaskObservationResponse,
    RobotTaskResultCallbackRequest,
    RobotTaskSimulateResponseRequest,
    RobotTaskStatusCallbackRequest,
    RobotTaskTimelineResponse,
    RobotTargetMoveRequest,
)
from backend.config import Settings
from backend.services.robot_gateway_service import RobotGatewayService
from backend.services.robot_task_service import RobotTaskService


router = APIRouter(prefix="/robot", tags=["robot"])


@router.get("/health")
async def robot_health(service: RobotGatewayService = Depends(get_robot_gateway_service)) -> dict:
    return service.health()


@router.get("/status")
async def robot_status(
    gateway: RobotGatewayService = Depends(get_robot_gateway_service),
    task_service: RobotTaskService = Depends(get_robot_task_service),
) -> dict:
    tasks = task_service.list_tasks(limit=20)
    current_task = next((task for task in tasks if task.status.value in {"QUEUED", "RUNNING", "BLOCKED"}), None)
    return {
        "ok": True,
        "gateway": gateway.status(),
        "task_center": {
            "persisted": True,
            "task_count": len(tasks),
            "current_task": current_task.model_dump(mode="json") if current_task else None,
        },
    }


@router.get("/tasks", response_model=RobotTaskListResponse)
async def robot_tasks(
    status: str | None = Query(default=None),
    elder_id: str | None = Query(default=None),
    outcome: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    service: RobotTaskService = Depends(get_robot_task_service),
) -> RobotTaskListResponse:
    return RobotTaskListResponse(
        tasks=service.list_tasks(status=status, elder_id=elder_id, outcome=outcome, limit=limit)
    )


@router.get("/tasks/{task_id}/timeline", response_model=RobotTaskTimelineResponse)
async def robot_task_timeline(
    task_id: str,
    service: RobotTaskService = Depends(get_robot_task_service),
) -> RobotTaskTimelineResponse:
    if service.get_task(task_id) is None:
        raise HTTPException(status_code=404, detail="ROBOT_TASK_NOT_FOUND")
    return RobotTaskTimelineResponse(timeline=service.list_timeline(task_id))


@router.get("/tasks/{task_id}/observation", response_model=RobotTaskObservationResponse)
async def robot_task_observation(
    task_id: str,
    service: RobotTaskService = Depends(get_robot_task_service),
) -> RobotTaskObservationResponse:
    if service.get_task(task_id) is None:
        raise HTTPException(status_code=404, detail="ROBOT_TASK_NOT_FOUND")
    return RobotTaskObservationResponse(observation=service.get_observation(task_id))


@router.get("/tasks/{task_id}/evidence/arrival.jpg", response_model=None)
async def robot_task_arrival_evidence(
    task_id: str,
    task_service: RobotTaskService = Depends(get_robot_task_service),
    gateway: RobotGatewayService = Depends(get_robot_gateway_service),
) -> Response:
    task = task_service.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="ROBOT_TASK_NOT_FOUND")
    observation = task_service.get_observation(task_id)
    if observation is not None and observation.snapshot_url and observation.snapshot_url.startswith(("http://", "https://")):
        url = observation.snapshot_url
    elif task.gateway_task_id:
        url = f"{gateway.base_url}/api/robot/tasks/{task.gateway_task_id}/evidence/arrival.jpg"
    else:
        raise HTTPException(status_code=404, detail="ROBOT_EVIDENCE_NOT_AVAILABLE")
    try:
        response = await asyncio.to_thread(requests.get, url, timeout=gateway.timeout_seconds)
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"ROBOT_EVIDENCE_UNAVAILABLE: {exc}") from exc
    if not response.ok:
        raise HTTPException(status_code=response.status_code, detail="ROBOT_EVIDENCE_UNAVAILABLE")
    content_type = response.headers.get("content-type") or "image/jpeg"
    if "image" not in content_type.lower():
        raise HTTPException(status_code=502, detail="ROBOT_EVIDENCE_NOT_IMAGE")
    return Response(content=response.content, media_type=content_type)


@router.post("/tasks/{task_id}/cancel", response_model=RobotTaskCancelResponse)
async def robot_task_cancel(
    task_id: str,
    service: RobotTaskService = Depends(get_robot_task_service),
) -> RobotTaskCancelResponse:
    task = await service.cancel_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="ROBOT_TASK_NOT_FOUND")
    return RobotTaskCancelResponse(task=task)


@router.post("/tasks/{task_id}/simulate-response", response_model=RobotCallbackAck)
async def robot_task_simulate_response(
    task_id: str,
    payload: RobotTaskSimulateResponseRequest,
    service: RobotTaskService = Depends(get_robot_task_service),
    settings: Settings = Depends(get_settings_dependency),
) -> RobotCallbackAck:
    if not settings.robot_simulation_enabled:
        raise HTTPException(status_code=403, detail="ROBOT_SIMULATION_DISABLED")
    ack = await service.simulate_response(
        task_id=task_id,
        response_type=payload.response_type,
        transcript=payload.transcript,
        snapshot_url=payload.snapshot_url,
    )
    if ack is None:
        raise HTTPException(status_code=404, detail="ROBOT_TASK_NOT_FOUND")
    return ack


@router.get("/tasks/{task_id}", response_model=RobotTaskDetailResponse)
async def robot_task(
    task_id: str,
    task_service: RobotTaskService = Depends(get_robot_task_service),
    gateway: RobotGatewayService = Depends(get_robot_gateway_service),
) -> RobotTaskDetailResponse:
    task = task_service.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="ROBOT_TASK_NOT_FOUND")
    gateway_payload = gateway.get_task(task.gateway_task_id) if task.gateway_task_id else None
    return RobotTaskDetailResponse(task=task, gateway=gateway_payload)


@router.post("/tasks/target-move")
async def robot_target_move(
    payload: RobotTargetMoveRequest,
    service: RobotGatewayService = Depends(get_robot_gateway_service),
) -> dict:
    return service.submit_target_move(payload)


@router.post("/events/fall")
async def robot_fall_event(
    payload: RobotFallEventRequest,
    service: RobotGatewayService = Depends(get_robot_gateway_service),
) -> dict:
    return service.submit_fall_event(payload)


@router.post("/callbacks/task-status", response_model=RobotCallbackAck)
async def robot_task_status_callback(
    payload: RobotTaskStatusCallbackRequest,
    service: RobotTaskService = Depends(get_robot_task_service),
) -> RobotCallbackAck:
    return await service.handle_status_callback(payload)


@router.post("/callbacks/task-result", response_model=RobotCallbackAck)
async def robot_task_result_callback(
    payload: RobotTaskResultCallbackRequest,
    service: RobotTaskService = Depends(get_robot_task_service),
) -> RobotCallbackAck:
    return await service.handle_result_callback(payload)
