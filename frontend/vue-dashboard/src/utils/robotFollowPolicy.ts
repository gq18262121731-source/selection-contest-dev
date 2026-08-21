export type RobotFollowTaskState =
  | "IDLE"
  | "REQUESTED"
  | "ACCEPTED"
  | "EXECUTING"
  | "COMPLETED"
  | "FAILED";

export type RobotFollowStateSource = "local-intent" | "robot";

export interface RobotFollowTaskSnapshot {
  state: RobotFollowTaskState;
  source: RobotFollowStateSource;
  reason: string;
  updatedAt: string | null;
}

export const INITIAL_ROBOT_FOLLOW_TASK: RobotFollowTaskSnapshot = {
  state: "IDLE",
  source: "local-intent",
  reason: "尚未登记跟随请求",
  updatedAt: null,
};

const ROBOT_TRANSITIONS: Record<RobotFollowTaskState, RobotFollowTaskState[]> = {
  IDLE: ["REQUESTED"],
  REQUESTED: ["IDLE", "ACCEPTED", "FAILED"],
  ACCEPTED: ["EXECUTING", "FAILED"],
  EXECUTING: ["COMPLETED", "FAILED"],
  COMPLETED: ["IDLE"],
  FAILED: ["IDLE"],
};

export function recordLocalFollowRequest(now = new Date()): RobotFollowTaskSnapshot {
  return {
    state: "REQUESTED",
    source: "local-intent",
    reason: "请求仅登记在当前页面，尚未发送至机器人，也未收到机器人确认",
    updatedAt: now.toISOString(),
  };
}

export function clearLocalFollowRequest(now = new Date()): RobotFollowTaskSnapshot {
  return {
    state: "IDLE",
    source: "local-intent",
    reason: "本地请求记录已撤销；未向机器人发送停止指令",
    updatedAt: now.toISOString(),
  };
}

export function applyRobotFollowState(
  current: RobotFollowTaskSnapshot,
  nextState: RobotFollowTaskState,
  reason: string,
  now = new Date(),
): RobotFollowTaskSnapshot {
  if (!ROBOT_TRANSITIONS[current.state].includes(nextState)) {
    throw new Error(`Invalid robot follow transition: ${current.state} -> ${nextState}`);
  }
  return {
    state: nextState,
    source: "robot",
    reason,
    updatedAt: now.toISOString(),
  };
}

export function robotFollowStateLabel(state: RobotFollowTaskState): string {
  const labels: Record<RobotFollowTaskState, string> = {
    IDLE: "未请求",
    REQUESTED: "请求已登记（未发送）",
    ACCEPTED: "机器人已接受",
    EXECUTING: "跟随执行中",
    COMPLETED: "跟随已完成",
    FAILED: "跟随失败",
  };
  return labels[state];
}
