import { assertMockRobotContract, isRobotRecord, RobotContractError } from "../api/robotContractPolicy";
import type {
  RobotPointCloudError,
  RobotPointCloudFrame,
  RobotPointCloudStreamInfo,
} from "../types/robot";

export type RobotPointCloudMessage =
  | RobotPointCloudStreamInfo
  | RobotPointCloudFrame
  | RobotPointCloudError
  | (Record<string, unknown> & {
      type: "connection_state_changed";
      connection_state: string;
      provider: "mock";
      real_motion_enabled: false;
      timestamp: string;
    });

function finiteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function invalid(endpoint: string, message: string): never {
  throw new RobotContractError("ROBOT_API_INVALID_ENVELOPE", endpoint, message);
}

export function validateRobotPointCloudMessage(
  value: unknown,
  endpoint = "/ws/robot/point-cloud",
): RobotPointCloudMessage {
  assertMockRobotContract(value, endpoint);
  if (!isRobotRecord(value) || typeof value.type !== "string" || typeof value.timestamp !== "string") {
    return invalid(endpoint, "Mock 点云消息基础结构无效");
  }

  if (value.type === "connection_state_changed") {
    if (typeof value.connection_state !== "string") return invalid(endpoint, "点云连接状态消息无效");
    return value as RobotPointCloudMessage;
  }

  if (value.type === "point_cloud_stream_info") {
    if (
      value.frame_id !== "mock_lidar"
      || value.coordinate_frame !== "map"
      || !finiteNumber(value.target_fps)
      || value.target_fps <= 0
      || value.target_fps > 5
      || !Number.isInteger(value.max_points)
      || (value.max_points as number) <= 0
      || (value.max_points as number) > 5000
      || !Number.isInteger(value.queue_size)
      || (value.queue_size as number) <= 0
      || (value.queue_size as number) > 2
    ) {
      return invalid(endpoint, "Mock 点云流说明不符合合同");
    }
    return value as unknown as RobotPointCloudStreamInfo;
  }

  if (value.type === "error") {
    if (typeof value.code !== "string" || typeof value.message !== "string") {
      return invalid(endpoint, "Mock 点云错误消息无效");
    }
    return value as unknown as RobotPointCloudError;
  }

  if (value.type !== "point_cloud_frame") return invalid(endpoint, "收到未支持的点云消息类型");
  if (
    !Number.isInteger(value.sequence)
    || (value.sequence as number) < 1
    || !Number.isInteger(value.point_count)
    || (value.point_count as number) < 0
    || (value.point_count as number) > 5000
    || !Array.isArray(value.points)
    || value.points.length !== value.point_count
  ) {
    return invalid(endpoint, "Mock 点云帧计数或序列无效");
  }
  for (const point of value.points) {
    if (!Array.isArray(point) || point.length !== 4 || !point.every(finiteNumber)) {
      return invalid(endpoint, "Mock 点云帧包含无效坐标");
    }
  }
  const robotPose = value.robot_pose;
  if (
    !isRobotRecord(robotPose)
    || !finiteNumber(robotPose.x)
    || !finiteNumber(robotPose.y)
    || !finiteNumber(robotPose.z)
    || !finiteNumber(robotPose.yaw)
  ) {
    return invalid(endpoint, "Mock 点云机器人位姿无效");
  }
  if (value.target_pose !== null && value.target_pose !== undefined) {
    const targetPose = value.target_pose;
    if (
      !isRobotRecord(targetPose)
      || !finiteNumber(targetPose.x)
      || !finiteNumber(targetPose.y)
      || !finiteNumber(targetPose.z)
      || !finiteNumber(targetPose.yaw)
    ) {
      return invalid(endpoint, "Mock 点云目标位姿无效");
    }
  }
  return value as unknown as RobotPointCloudFrame;
}
