from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Sequence
from uuid import uuid4

from backend.models.robot_navigation_model import (
    RobotMap,
    RobotMapPoint,
    RobotMapPointStatus,
    RobotMapPointType,
    RobotMapStatus,
    RobotPatrolRoute,
    RobotPatrolRoutePoint,
    RobotPatrolRouteStatus,
)
from backend.repositories.robot_map_repo import RobotMapRepository
from backend.services.robot_navigation_errors import (
    RobotNavigationErrorCode,
    RobotNavigationServiceError,
)


class RobotMapService:
    """Business source of truth for Mock maps, points, and patrol routes."""

    def __init__(self, repository: RobotMapRepository) -> None:
        self.repository = repository

    def create_draft_map(
        self,
        name: str,
        *,
        map_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> RobotMap:
        item = RobotMap(
            map_id=map_id or f"map_{uuid4().hex}",
            name=name,
            status=RobotMapStatus.DRAFT,
            metadata=metadata or {},
        )
        return self.repository.create_map(item)

    def mark_preview_ready(self, map_id: str, *, metadata: dict[str, Any] | None = None) -> RobotMap:
        item = self.require_map(map_id)
        if item.status not in {RobotMapStatus.DRAFT, RobotMapStatus.PREVIEW}:
            self._raise(RobotNavigationErrorCode.MAP_STATE_CONFLICT, "只有草稿地图可以进入预览状态")
        merged_metadata = {**item.metadata, **(metadata or {})}
        return self.repository.update_map(
            item.model_copy(update={"status": RobotMapStatus.PREVIEW, "metadata": merged_metadata})
        )

    def activate_preview(self, map_id: str, *, replacement_confirmed: bool) -> RobotMap:
        target = self.require_map(map_id)
        if target.status != RobotMapStatus.PREVIEW:
            self._raise(RobotNavigationErrorCode.MAP_STATE_CONFLICT, "正式保存前地图必须处于 preview 状态")
        active = self.repository.get_active_map()
        if active and active.map_id != map_id and not replacement_confirmed:
            self._raise(
                RobotNavigationErrorCode.MAP_REPLACEMENT_CONFIRMATION_REQUIRED,
                "替换当前活动地图需要人工确认",
                details={"active_map_id": active.map_id},
            )
        try:
            return self.repository.activate_map(map_id)
        except ValueError as exc:
            self._translate_repository_error(exc)

    def require_map(self, map_id: str) -> RobotMap:
        item = self.repository.get_map(map_id)
        if item is None:
            self._raise(RobotNavigationErrorCode.MAP_NOT_FOUND, "地图不存在", details={"map_id": map_id})
        return item

    def require_active_map(self) -> RobotMap:
        item = self.repository.get_active_map()
        if item is None:
            self._raise(RobotNavigationErrorCode.MAP_NOT_ACTIVE, "当前没有活动地图")
        return item

    def save_point(self, point: RobotMapPoint) -> RobotMapPoint:
        map_item = self.require_map(point.map_id)
        if map_item.status not in {RobotMapStatus.PREVIEW, RobotMapStatus.ACTIVE}:
            self._raise(RobotNavigationErrorCode.MAP_STATE_CONFLICT, "仅预览或活动地图可以维护点位")
        if point.status == RobotMapPointStatus.VALID and point.point_type in {
            RobotMapPointType.HOME,
            RobotMapPointType.OBSERVATION,
        }:
            area_id = point.metadata.get("area_id")
            if point.point_type == RobotMapPointType.OBSERVATION and not area_id:
                self._raise(RobotNavigationErrorCode.MAP_POINT_INVALID, "观察点必须声明 area_id")
            duplicate = next(
                (
                    item
                    for item in self.repository.list_points(point.map_id, include_invalid=False)
                    if item.point_type == point.point_type and item.point_id != point.point_id
                    and (
                        point.point_type == RobotMapPointType.HOME
                        or item.metadata.get("area_id") == area_id
                    )
                ),
                None,
            )
            if duplicate:
                self._raise(
                    RobotNavigationErrorCode.MAP_POINT_INVALID,
                    "同一地图中的 home 点或同一区域 observation 点必须唯一",
                    details={"existing_point_id": duplicate.point_id, "point_type": point.point_type.value, "area_id": area_id},
                )
        try:
            return self.repository.save_point(point)
        except ValueError as exc:
            self._translate_repository_error(exc)

    def invalidate_point(self, point_id: str) -> RobotMapPoint:
        point = self.repository.get_point(point_id)
        if point is None:
            self._raise(RobotNavigationErrorCode.MAP_POINT_NOT_FOUND, "点位不存在", details={"point_id": point_id})
        now = datetime.now(timezone.utc)
        return self.repository.save_point(
            point.model_copy(update={"status": RobotMapPointStatus.INVALID, "invalidated_at": now, "updated_at": now})
        )

    def require_valid_point(
        self,
        point_id: str,
        *,
        map_id: str | None = None,
        point_type: RobotMapPointType | None = None,
    ) -> RobotMapPoint:
        point = self.repository.get_point(point_id)
        if point is None:
            self._raise(RobotNavigationErrorCode.MAP_POINT_NOT_FOUND, "点位不存在", details={"point_id": point_id})
        if (
            point.status != RobotMapPointStatus.VALID
            or (map_id is not None and point.map_id != map_id)
            or (point_type is not None and point.point_type != point_type)
        ):
            self._raise(RobotNavigationErrorCode.MAP_POINT_INVALID, "点位不可用于当前任务", details={"point_id": point_id})
        return point

    def find_observation_point(self, map_id: str, area_id: str) -> RobotMapPoint:
        candidates = [
            point
            for point in self.repository.list_points(map_id, include_invalid=False)
            if point.point_type == RobotMapPointType.OBSERVATION
            and point.metadata.get("area_id") == area_id
        ]
        if len(candidates) != 1:
            self._raise(
                RobotNavigationErrorCode.OBSERVATION_POINT_NOT_FOUND,
                "区域未配置唯一有效观察点",
                details={"map_id": map_id, "area_id": area_id},
            )
        return candidates[0]

    def require_home_point(self, map_id: str) -> RobotMapPoint:
        candidates = [
            point
            for point in self.repository.list_points(map_id, include_invalid=False)
            if point.point_type == RobotMapPointType.HOME
        ]
        if len(candidates) != 1:
            self._raise(
                RobotNavigationErrorCode.HOME_POINT_NOT_FOUND,
                "活动地图未配置唯一有效返航点",
                details={"map_id": map_id},
            )
        return candidates[0]

    def save_route(
        self,
        route: RobotPatrolRoute,
        points: Sequence[RobotPatrolRoutePoint],
    ) -> RobotPatrolRoute:
        active = self.require_active_map()
        if route.map_id != active.map_id or route.status not in {
            RobotPatrolRouteStatus.VALID,
            RobotPatrolRouteStatus.ACTIVE,
        }:
            self._raise(RobotNavigationErrorCode.ROUTE_INVALID, "巡逻路线必须属于活动地图并处于有效状态")
        for item in points:
            self.require_valid_point(item.point_id, map_id=route.map_id, point_type=RobotMapPointType.PATROL)
        try:
            return self.repository.save_route(route, points)
        except ValueError as exc:
            self._translate_repository_error(exc)

    def require_valid_route(self, route_id: str) -> tuple[RobotPatrolRoute, list[RobotPatrolRoutePoint]]:
        value = self.repository.get_route(route_id)
        if value is None:
            self._raise(RobotNavigationErrorCode.ROUTE_NOT_FOUND, "巡逻路线不存在", details={"route_id": route_id})
        route, points = value
        active = self.require_active_map()
        if route.map_id != active.map_id or route.status not in {
            RobotPatrolRouteStatus.VALID,
            RobotPatrolRouteStatus.ACTIVE,
        } or not points:
            self._raise(RobotNavigationErrorCode.ROUTE_INVALID, "巡逻路线不可用于当前活动地图")
        for item in points:
            self.require_valid_point(item.point_id, map_id=route.map_id, point_type=RobotMapPointType.PATROL)
        return route, points

    @staticmethod
    def _raise(code: RobotNavigationErrorCode, message: str, *, details: dict[str, Any] | None = None) -> None:
        raise RobotNavigationServiceError(code, message, details=details)

    @classmethod
    def _translate_repository_error(cls, exc: ValueError) -> None:
        code = str(exc)
        mapped = RobotNavigationErrorCode.__members__.get(code, RobotNavigationErrorCode.OPERATION_CONFLICT)
        cls._raise(mapped, "地图数据校验失败", details={"repository_code": code})
