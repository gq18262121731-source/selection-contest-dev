import type {
  RobotConnectionState,
  RobotControlOwner,
  RobotMappingState,
  RobotNavigationExecutionState,
} from "../types/robot";

export const MOCK_ENVIRONMENT_NOTICE = "当前为模拟导航环境，真实机器人运动控制已禁用。";

const connectionLabels: Record<RobotConnectionState, string> = {
  idle: "未连接",
  connecting: "连接中",
  connected: "已连接",
  reconnecting: "正在重连",
  disconnected: "已断开",
  error: "异常",
};

const executionStateLabels: Record<RobotNavigationExecutionState, string> = {
  created: "已创建",
  safety_checking: "安全检查中",
  blocked: "阻塞",
  queued: "排队中",
  navigating: "导航中",
  paused_manual: "已暂停（遥控接管）",
  paused_admin: "已暂停（管理员）",
  arrived: "已到达",
  voice_prompting: "模拟语音询问中",
  waiting_response: "等待老人回应",
  safe_response: "老人已明确回应",
  help_requested: "老人请求帮助",
  no_response: "15 秒内无有效回应",
  uncertain: "无法可靠判断老人状态",
  waiting_admin_confirmation: "等待管理员确认",
  returning_home: "模拟返航中",
  completed: "已完成",
  failed: "异常",
  cancelled: "已取消",
};

const mappingStateLabels: Record<RobotMappingState, string> = {
  idle: "待命",
  mapping: "模拟建图中",
  preview_ready: "预览待确认",
  saved: "已保存",
  cancelled: "已取消",
  failed: "异常",
};

const controlOwnerLabels: Record<RobotControlOwner, string> = {
  NONE: "无控制方",
  MANUAL: "遥控器",
  NAVIGATION: "导航任务",
  FOLLOW: "跟随任务",
  EMERGENCY_STOP: "急停",
};

const blockedReasonLabels: Record<string, string> = {
  ROBOT_OFFLINE: "机器人离线",
  EMERGENCY_STOP_ACTIVE: "急停未解除",
  LOCALIZATION_INVALID: "定位无效",
  MAP_NOT_LOADED: "地图未加载",
  PATH_NOT_PLANNABLE: "路径不可规划",
  ROBOT_NOT_STATIONARY: "机器人未静止",
  CONTROL_NOT_AVAILABLE: "控制权不可用",
  MANUAL_CONTROL_ACTIVE: "遥控器正在接管",
  SAFE_RESPONSE_REQUIRED: "需要老人明确回应安全",
  HOME_POINT_NOT_FOUND: "未配置机器人待命点",
  OBSERVATION_POINT_NOT_FOUND: "未配置活动区观察点",
  ACTIVE_MAP_NOT_FOUND: "未找到当前地图",
  RETURN_NOT_IN_PROGRESS: "当前未处于返航状态",
};

export function robotConnectionLabel(value: RobotConnectionState | null | undefined) {
  return value ? connectionLabels[value] : "未验证";
}

export function robotExecutionStateLabel(value: string | null | undefined) {
  if (!value) return "未验证";
  return executionStateLabels[value as RobotNavigationExecutionState] ?? value;
}

export function robotMappingStateLabel(value: string | null | undefined) {
  if (!value) return "未验证";
  return mappingStateLabels[value as RobotMappingState] ?? value;
}

export function robotControlOwnerLabel(value: RobotControlOwner | null | undefined) {
  return value ? controlOwnerLabels[value] : "无控制方";
}

export function robotBlockedReason(code: string) {
  return blockedReasonLabels[code] ?? "未识别的安全阻断原因";
}
