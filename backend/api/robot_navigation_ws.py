from __future__ import annotations

import asyncio
from contextlib import suppress
from typing import Any, Callable

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.dependencies import (
    get_robot_navigation_application_service,
    get_robot_navigation_event_hub,
    get_robot_navigation_ws_proxy_service,
)
from backend.services.robot_navigation_application_service import RobotNavigationApplicationService
from backend.services.robot_navigation_errors import RobotNavigationServiceError
from backend.services.robot_navigation_event_hub import RobotEventSubscription, RobotNavigationEventHub
from backend.services.robot_navigation_ws_proxy_service import RobotNavigationWsProxyService


router = APIRouter(tags=["robot-navigation-websocket"])


def _component(websocket: WebSocket, state_name: str, fallback: Callable[[], Any]) -> Any:
    return getattr(websocket.app.state, state_name, None) or fallback()


async def _serve_channel(
    websocket: WebSocket,
    *,
    channel: str,
    snapshot_type: str,
    snapshot_loader: Callable[[], dict[str, Any]],
    incident_id: str | None = None,
    use_upstream: bool = True,
) -> None:
    hub: RobotNavigationEventHub = _component(
        websocket, "robot_navigation_event_hub", get_robot_navigation_event_hub
    )
    proxy: RobotNavigationWsProxyService | None = None
    subscription: RobotEventSubscription | None = None
    receive_task: asyncio.Task[Any] | None = None
    queue_task: asyncio.Task[Any] | None = None
    await websocket.accept()
    try:
        subscription = hub.subscribe(channel, incident_id=incident_id)  # type: ignore[arg-type]
        if use_upstream:
            proxy = _component(
                websocket,
                "robot_navigation_ws_proxy_service",
                get_robot_navigation_ws_proxy_service,
            )
            await proxy.acquire()
        snapshot = await asyncio.to_thread(snapshot_loader)
        await websocket.send_json(hub.make_event(snapshot_type, snapshot))
        while True:
            receive_task = asyncio.create_task(websocket.receive_json())
            queue_task = asyncio.create_task(subscription.queue.get())
            done, pending = await asyncio.wait(
                {receive_task, queue_task}, return_when=asyncio.FIRST_COMPLETED
            )
            for task in pending:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
            if queue_task in done:
                event = queue_task.result()
                if event is None:
                    break
                await websocket.send_json(event)
                continue
            message = receive_task.result()
            if isinstance(message, dict) and message.get("type") == "sync":
                snapshot = await asyncio.to_thread(snapshot_loader)
                await websocket.send_json(hub.make_event(snapshot_type, snapshot))
    except WebSocketDisconnect:
        pass
    except RobotNavigationServiceError as exc:
        await websocket.send_json(
            hub.make_event(
                "error",
                {"code": exc.code, "message": exc.message, "details": exc.details},
            )
        )
        with suppress(RuntimeError):
            await websocket.close(code=4404 if exc.code == "INCIDENT_NOT_FOUND" else 1011)
    finally:
        for task in (receive_task, queue_task):
            if task and not task.done():
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
        if subscription:
            hub.unsubscribe(subscription)
        if proxy:
            await proxy.release()


@router.websocket("/ws/robot/status")
async def robot_status_websocket(websocket: WebSocket) -> None:
    service: RobotNavigationApplicationService = _component(
        websocket,
        "robot_navigation_application_service",
        get_robot_navigation_application_service,
    )
    await _serve_channel(
        websocket,
        channel="status",
        snapshot_type="robot_status_snapshot",
        snapshot_loader=service.status_snapshot,
    )


@router.websocket("/ws/robot/navigation")
async def robot_navigation_websocket(websocket: WebSocket) -> None:
    service: RobotNavigationApplicationService = _component(
        websocket,
        "robot_navigation_application_service",
        get_robot_navigation_application_service,
    )
    await _serve_channel(
        websocket,
        channel="navigation",
        snapshot_type="navigation_snapshot",
        snapshot_loader=service.navigation_snapshot,
    )


@router.websocket("/ws/robot/emergency/{incident_id}")
async def robot_emergency_websocket(websocket: WebSocket, incident_id: str) -> None:
    service: RobotNavigationApplicationService = _component(
        websocket,
        "robot_navigation_application_service",
        get_robot_navigation_application_service,
    )
    await _serve_channel(
        websocket,
        channel="emergency",
        snapshot_type="emergency_snapshot",
        snapshot_loader=lambda: service.emergency_bundle(incident_id),
        incident_id=incident_id,
        use_upstream=False,
    )
