from __future__ import annotations

import asyncio
from contextlib import suppress
from typing import Any, Callable

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.dependencies import (
    get_robot_point_cloud_hub,
    get_robot_point_cloud_ws_proxy_service,
)
from backend.schemas.robot_point_cloud_schema import local_point_cloud_error
from backend.services.robot_point_cloud_hub import RobotPointCloudHub, RobotPointCloudSubscription
from backend.services.robot_point_cloud_ws_proxy_service import RobotPointCloudWsProxyService


router = APIRouter(tags=["robot-point-cloud-websocket"])


def _component(websocket: WebSocket, state_name: str, fallback: Callable[[], Any]) -> Any:
    return getattr(websocket.app.state, state_name, None) or fallback()


async def _send_snapshot(websocket: WebSocket, hub: RobotPointCloudHub) -> None:
    stream_info, latest_frame = hub.snapshot()
    if stream_info is not None:
        await websocket.send_json(stream_info)
    if latest_frame is not None:
        await websocket.send_json(latest_frame)


@router.websocket("/ws/robot/point-cloud")
async def robot_point_cloud_websocket(websocket: WebSocket) -> None:
    hub: RobotPointCloudHub = _component(
        websocket, "robot_point_cloud_hub", get_robot_point_cloud_hub
    )
    proxy: RobotPointCloudWsProxyService = _component(
        websocket,
        "robot_point_cloud_ws_proxy_service",
        get_robot_point_cloud_ws_proxy_service,
    )
    subscription: RobotPointCloudSubscription | None = None
    active_tasks: set[asyncio.Task[Any]] = set()
    await websocket.accept()
    try:
        subscription = hub.subscribe()
        await _send_snapshot(websocket, hub)
        await proxy.acquire()
        while True:
            receive_task = asyncio.create_task(websocket.receive_json())
            control_task = asyncio.create_task(subscription.control_queue.get())
            frame_task = asyncio.create_task(subscription.frame_queue.get())
            active_tasks = {receive_task, control_task, frame_task}
            done, pending = await asyncio.wait(
                active_tasks, return_when=asyncio.FIRST_COMPLETED
            )
            for task in pending:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
            should_close = False
            if control_task in done:
                message = control_task.result()
                if message is None:
                    should_close = True
                else:
                    await websocket.send_json(message)
            if frame_task in done:
                message = frame_task.result()
                if message is None:
                    should_close = True
                else:
                    hub.mark_frame_consumed(subscription)
                    await websocket.send_json(message)
            if should_close:
                break
            if receive_task not in done:
                continue
            message = receive_task.result()
            message_type = message.get("type") if isinstance(message, dict) else None
            if message_type == "sync":
                await _send_snapshot(websocket, hub)
                if not await proxy.request_sync():
                    await websocket.send_json(
                        local_point_cloud_error(
                            "POINT_CLOUD_PROXY_NOT_READY", "Mock 点云上游尚未连接"
                        )
                    )
                continue
            if message_type == "pong":
                continue
            await websocket.send_json(
                local_point_cloud_error(
                    "ROBOT_POINT_CLOUD_INVALID_MESSAGE",
                    "仅支持 sync 和 pong；客户端不得上传或修改点云",
                )
            )
    except WebSocketDisconnect:
        pass
    except (TypeError, ValueError):
        with suppress(WebSocketDisconnect, RuntimeError):
            await websocket.send_json(
                local_point_cloud_error(
                    "ROBOT_POINT_CLOUD_INVALID_MESSAGE", "客户端消息必须是 JSON 对象"
                )
            )
    finally:
        for task in active_tasks:
            if not task.done():
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
        if subscription is not None:
            hub.unsubscribe(subscription)
            await proxy.release()
