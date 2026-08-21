from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path

from backend.api.robot_navigation_api import invoke
from backend.dependencies import get_robot_navigation_application_service
from backend.schemas.robot_emergency_api_schema import (
    RobotEmergencyAcknowledgeRequest,
    RobotEmergencyDialogueRequest,
    RobotEmergencyDispatchRequest,
    RobotEmergencyMockDialogueStartRequest,
    RobotEmergencyMockReturnCompleteRequest,
    RobotEmergencyResolveRequest,
)
from backend.schemas.robot_navigation_api_schema import RobotTaskOperationRequest
from backend.services.robot_navigation_application_service import RobotNavigationApplicationService


router = APIRouter(prefix="/robot/emergency", tags=["robot-emergency"])
IncidentId = Annotated[str, Path(min_length=1, max_length=160)]


@router.get("/{incident_id}")
async def emergency_detail(incident_id: IncidentId, service: RobotNavigationApplicationService = Depends(get_robot_navigation_application_service)):
    return await invoke(lambda: service.emergency_bundle(incident_id))


@router.post("/{incident_id}/dispatch")
async def dispatch(incident_id: IncidentId, body: RobotEmergencyDispatchRequest, service: RobotNavigationApplicationService = Depends(get_robot_navigation_application_service)):
    return await invoke(lambda: service.dispatch_emergency(incident_id, body), request_id=body.request_id, created=True)


@router.post("/{incident_id}/acknowledge")
async def acknowledge(incident_id: IncidentId, body: RobotEmergencyAcknowledgeRequest, service: RobotNavigationApplicationService = Depends(get_robot_navigation_application_service)):
    return await invoke(lambda: service.acknowledge_emergency(incident_id, body), request_id=body.request_id)


@router.post("/{incident_id}/resume")
async def resume(incident_id: IncidentId, body: RobotTaskOperationRequest, service: RobotNavigationApplicationService = Depends(get_robot_navigation_application_service)):
    return await invoke(lambda: service.resume_emergency(incident_id, body.request_id), request_id=body.request_id)


@router.post("/{incident_id}/escalate")
async def escalate(incident_id: IncidentId, body: RobotEmergencyDialogueRequest, service: RobotNavigationApplicationService = Depends(get_robot_navigation_application_service)):
    return await invoke(lambda: service.record_dialogue(incident_id, body), request_id=body.request_id)


@router.post("/{incident_id}/resolve-and-return")
async def resolve_and_return(incident_id: IncidentId, body: RobotEmergencyResolveRequest, service: RobotNavigationApplicationService = Depends(get_robot_navigation_application_service)):
    return await invoke(lambda: service.resolve_and_return(incident_id, body), request_id=body.request_id)


@router.get("/{incident_id}/dialogue")
async def dialogue(incident_id: IncidentId, service: RobotNavigationApplicationService = Depends(get_robot_navigation_application_service)):
    return await invoke(lambda: service.dialogue(incident_id))


@router.post("/{incident_id}/mock/dialogue/start")
async def start_mock_dialogue(
    incident_id: IncidentId,
    body: RobotEmergencyMockDialogueStartRequest,
    service: RobotNavigationApplicationService = Depends(get_robot_navigation_application_service),
):
    return await invoke(
        lambda: service.start_mock_emergency_dialogue(incident_id, body),
        request_id=body.request_id,
    )


@router.post("/{incident_id}/mock/return/complete")
async def complete_mock_return(
    incident_id: IncidentId,
    body: RobotEmergencyMockReturnCompleteRequest,
    service: RobotNavigationApplicationService = Depends(get_robot_navigation_application_service),
):
    return await invoke(
        lambda: service.complete_mock_emergency_return(incident_id, body),
        request_id=body.request_id,
    )
