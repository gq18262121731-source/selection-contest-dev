from __future__ import annotations

import asyncio
from typing import Annotated, Any, Callable

from fastapi import APIRouter, Depends, Path, Query
from fastapi.responses import JSONResponse

from backend.dependencies import get_robot_navigation_application_service
from backend.schemas.robot_navigation_api_schema import (
    RobotMapPreviewRequest,
    RobotMapSaveRequest,
    RobotMappingStartRequest,
    RobotMappingStopRequest,
    RobotPatrolStartRequest,
    RobotPointCreateRequest,
    RobotPointUpdateRequest,
    RobotRouteCreateRequest,
    RobotTaskOperationRequest,
    error_envelope,
    success_envelope,
)
from backend.services.robot_navigation_application_service import (
    RobotApplicationResult,
    RobotNavigationApplicationService,
)
from backend.services.robot_navigation_errors import RobotNavigationServiceError


router = APIRouter(prefix="/robot", tags=["robot-navigation"])
Identifier = Annotated[str, Path(min_length=1, max_length=160)]


ERROR_HTTP_STATUS = {
    "ROBOT_GATEWAY_TIMEOUT": 504,
    "ROBOT_GATEWAY_UNAVAILABLE": 503,
    "ROBOT_GATEWAY_INVALID_RESPONSE": 502,
    "MOCK_PROVIDER_CONTRACT_VIOLATION": 502,
    "REAL_MOTION_DISABLED": 502,
    "MAP_NOT_FOUND": 404,
    "MAP_NOT_ACTIVE": 404,
    "MAP_POINT_NOT_FOUND": 404,
    "ROUTE_NOT_FOUND": 404,
    "TASK_NOT_FOUND": 404,
    "INCIDENT_NOT_FOUND": 404,
    "SAFETY_INTERLOCK_BLOCKED": 409,
    "INVALID_STATE_TRANSITION": 409,
    "DIALOGUE_ALREADY_STARTED": 409,
    "RETURN_NOT_IN_PROGRESS": 409,
    "SAFE_RESPONSE_REQUIRED": 409,
    "MAP_STATE_CONFLICT": 409,
    "MAP_REPLACEMENT_CONFIRMATION_REQUIRED": 409,
    "IDEMPOTENCY_CONFLICT": 409,
    "CONTROL_OWNER_CONFLICT": 409,
    "INCIDENT_STATE_CONFLICT": 409,
}


async def invoke(
    operation: Callable[[], Any],
    *,
    request_id: str | None = None,
    created: bool = False,
) -> JSONResponse:
    try:
        result = await asyncio.to_thread(operation)
    except RobotNavigationServiceError as exc:
        return JSONResponse(
            status_code=ERROR_HTTP_STATUS.get(exc.code, 400),
            content=error_envelope(exc.code, exc.message, exc.details, request_id),
        )
    replayed = isinstance(result, RobotApplicationResult) and result.replayed
    data = result.data if isinstance(result, RobotApplicationResult) else result
    return JSONResponse(
        status_code=201 if created and not replayed else 200,
        content=success_envelope(data, request_id),
    )


@router.get("/navigation/capabilities")
async def capabilities(service: RobotNavigationApplicationService = Depends(get_robot_navigation_application_service)):
    return await invoke(service.capabilities)


@router.get("/navigation/state")
async def navigation_state(service: RobotNavigationApplicationService = Depends(get_robot_navigation_application_service)):
    return await invoke(service.navigation_snapshot)


@router.get("/status/diagnostics")
async def diagnostics(service: RobotNavigationApplicationService = Depends(get_robot_navigation_application_service)):
    return await invoke(service.diagnostics)


@router.post("/navigation/mapping/start")
async def start_mapping(body: RobotMappingStartRequest, service: RobotNavigationApplicationService = Depends(get_robot_navigation_application_service)):
    return await invoke(lambda: service.start_mapping(body), request_id=body.request_id, created=True)


@router.post("/navigation/mapping/stop")
async def stop_mapping(body: RobotMappingStopRequest, service: RobotNavigationApplicationService = Depends(get_robot_navigation_application_service)):
    return await invoke(lambda: service.stop_mapping(body), request_id=body.request_id)


@router.post("/navigation/maps/preview")
async def preview_map(body: RobotMapPreviewRequest, service: RobotNavigationApplicationService = Depends(get_robot_navigation_application_service)):
    return await invoke(lambda: service.preview_map(body), request_id=body.request_id)


@router.post("/navigation/maps/save")
async def save_map(body: RobotMapSaveRequest, service: RobotNavigationApplicationService = Depends(get_robot_navigation_application_service)):
    return await invoke(lambda: service.save_map(body), request_id=body.request_id)


@router.get("/navigation/maps")
async def list_maps(service: RobotNavigationApplicationService = Depends(get_robot_navigation_application_service)):
    return await invoke(service.list_maps)


@router.get("/navigation/maps/active")
async def active_map(service: RobotNavigationApplicationService = Depends(get_robot_navigation_application_service)):
    return await invoke(service.active_map)


@router.get("/navigation/points")
async def list_points(map_id: str | None = Query(default=None, min_length=1, max_length=160), service: RobotNavigationApplicationService = Depends(get_robot_navigation_application_service)):
    return await invoke(lambda: service.list_points(map_id))


@router.post("/navigation/points")
async def create_point(body: RobotPointCreateRequest, service: RobotNavigationApplicationService = Depends(get_robot_navigation_application_service)):
    return await invoke(lambda: service.create_point(body), request_id=body.request_id, created=True)


@router.put("/navigation/points/{point_id}")
async def update_point(point_id: Identifier, body: RobotPointUpdateRequest, service: RobotNavigationApplicationService = Depends(get_robot_navigation_application_service)):
    return await invoke(lambda: service.update_point(point_id, body), request_id=body.request_id)


@router.delete("/navigation/points/{point_id}")
async def delete_point(point_id: Identifier, request_id: str = Query(min_length=1, max_length=160), service: RobotNavigationApplicationService = Depends(get_robot_navigation_application_service)):
    return await invoke(lambda: service.delete_point(point_id, request_id), request_id=request_id)


@router.get("/navigation/routes")
async def list_routes(map_id: str | None = Query(default=None, min_length=1, max_length=160), service: RobotNavigationApplicationService = Depends(get_robot_navigation_application_service)):
    return await invoke(lambda: service.list_routes(map_id))


@router.post("/navigation/routes")
async def create_route(body: RobotRouteCreateRequest, service: RobotNavigationApplicationService = Depends(get_robot_navigation_application_service)):
    return await invoke(lambda: service.create_route(body), request_id=body.request_id, created=True)


@router.get("/navigation/routes/{route_id}")
async def route_detail(route_id: Identifier, service: RobotNavigationApplicationService = Depends(get_robot_navigation_application_service)):
    return await invoke(lambda: service.route_detail(route_id))


@router.post("/navigation/routes/{route_id}/start")
async def start_patrol(route_id: Identifier, body: RobotPatrolStartRequest, service: RobotNavigationApplicationService = Depends(get_robot_navigation_application_service)):
    return await invoke(lambda: service.start_patrol(route_id, body), request_id=body.request_id, created=True)


@router.post("/navigation/tasks/{task_id}/pause")
async def pause_task(task_id: Identifier, body: RobotTaskOperationRequest, service: RobotNavigationApplicationService = Depends(get_robot_navigation_application_service)):
    return await invoke(lambda: service.pause_task(task_id, body.request_id), request_id=body.request_id)


@router.post("/navigation/tasks/{task_id}/resume")
async def resume_task(task_id: Identifier, body: RobotTaskOperationRequest, service: RobotNavigationApplicationService = Depends(get_robot_navigation_application_service)):
    return await invoke(lambda: service.resume_task(task_id, body.request_id), request_id=body.request_id)


@router.post("/navigation/tasks/{task_id}/stop")
async def stop_task(task_id: Identifier, body: RobotTaskOperationRequest, service: RobotNavigationApplicationService = Depends(get_robot_navigation_application_service)):
    return await invoke(lambda: service.stop_task(task_id, body.request_id), request_id=body.request_id)


@router.post("/navigation/tasks/{task_id}/manual-acquire")
async def manual_acquire(task_id: Identifier, body: RobotTaskOperationRequest, service: RobotNavigationApplicationService = Depends(get_robot_navigation_application_service)):
    return await invoke(lambda: service.manual_acquire(task_id, body.request_id), request_id=body.request_id)


@router.post("/navigation/tasks/{task_id}/manual-release")
async def manual_release(task_id: Identifier, body: RobotTaskOperationRequest, service: RobotNavigationApplicationService = Depends(get_robot_navigation_application_service)):
    return await invoke(lambda: service.manual_release(task_id, body.request_id), request_id=body.request_id)


@router.get("/tasks/{task_id}/navigation-events")
async def task_navigation_events(task_id: Identifier, service: RobotNavigationApplicationService = Depends(get_robot_navigation_application_service)):
    return await invoke(lambda: service.task_navigation_events(task_id))


@router.get("/tasks/{task_id}/dialogue")
async def task_dialogue(task_id: Identifier, service: RobotNavigationApplicationService = Depends(get_robot_navigation_application_service)):
    return await invoke(lambda: service.task_dialogue(task_id))


@router.get("/navigation/tasks/{task_id}/timeline")
async def navigation_task_timeline_alias(task_id: Identifier, service: RobotNavigationApplicationService = Depends(get_robot_navigation_application_service)):
    """Envelope alias; the legacy /robot/tasks/{task_id}/timeline response stays unchanged."""
    return await invoke(lambda: service.timeline(task_id))
