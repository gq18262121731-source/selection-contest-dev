export type MockProvider = "mock";
export type RealMotionDisabled = false;

export interface ApiEnvelope<T> {
  success: boolean;
  code: string;
  message: string;
  data: T;
  timestamp: string;
  request_id?: string | null;
}

export type CapabilityState = "mock" | "unavailable" | "not_verified" | "blocked" | "ready";
export type RobotCapabilityStatus = "READY" | "NOT_READY" | "UNKNOWN";

export type RobotControlOwner =
  | "NONE"
  | "MANUAL"
  | "NAVIGATION"
  | "FOLLOW"
  | "EMERGENCY_STOP";

export type RobotConnectionState =
  | "idle"
  | "connecting"
  | "connected"
  | "reconnecting"
  | "disconnected"
  | "error";

export type RobotPointCloudConnectionState = RobotConnectionState;

export interface MockRobotContract {
  provider: MockProvider;
  real_motion_enabled: RealMotionDisabled;
}

export interface RobotNavigationCapability extends MockRobotContract {
  mapping?: CapabilityState;
  maps?: CapabilityState;
  map_preview?: CapabilityState;
  map_save?: CapabilityState;
  navigation?: CapabilityState;
  point_navigation?: CapabilityState;
  path_planning?: CapabilityState;
  patrol?: CapabilityState;
  return_home?: CapabilityState;
  manual_takeover?: CapabilityState;
  localization?: CapabilityState;
  point_cloud?: CapabilityState;
  audio_input?: CapabilityState;
  audio_output?: CapabilityState;
  ros2?: CapabilityState;
  nav2?: CapabilityState;
  slam_toolbox?: CapabilityState;
  real_lidar_point_cloud?: CapabilityState;
  [key: string]: unknown;
}

export interface RobotSafetyChecks {
  robot_online: boolean;
  emergency_stop_clear: boolean;
  localization_valid: boolean;
  map_loaded: boolean;
  path_plannable: boolean;
  robot_stationary: boolean;
  control_available: boolean;
}

export interface RobotSafetyInterlock extends MockRobotContract {
  passed: boolean;
  checks: RobotSafetyChecks;
  blocked_by: string[];
  checked_at?: string;
}

export interface RobotTaskSummary {
  task_id: string;
  status?: string;
  execution_state?: string;
  control_owner?: RobotControlOwner;
  task_type?: string;
  elder_name?: string;
  elder_id?: string;
  location?: string;
  risk_level?: string;
  updated_at?: string;
  provider?: MockProvider;
  real_motion_enabled?: RealMotionDisabled;
  [key: string]: unknown;
}

export interface RobotMapSummary {
  map_id?: string;
  name?: string;
  status?: string;
  updated_at?: string;
  [key: string]: unknown;
}

export interface RobotLidarDiagnostics {
  status?: CapabilityState | string;
  available?: boolean | null;
  device_detected?: boolean | null;
  topic_discovered?: boolean | null;
  sample_received?: boolean | null;
  data_fresh?: boolean | null;
  mapping_prerequisites_ready?: boolean | null;
  mapping_ready?: boolean | null;
  reason?: string | null;
  error_code?: string | null;
  message?: string | null;
  checked_at?: string | null;
  [key: string]: unknown;
}

export interface RobotNavigationState extends MockRobotContract {
  robot_id?: string | null;
  robot_online?: boolean;
  network_reachable?: boolean;
  dds_initialized?: boolean;
  dds_state_available?: boolean;
  motion_ready?: boolean;
  emergency_stop_clear?: boolean;
  emergency_stop_active?: boolean;
  localization_valid?: boolean;
  map_loaded?: boolean;
  path_plannable?: boolean;
  robot_stationary?: boolean;
  control_available?: boolean;
  execution_state?: RobotNavigationExecutionState;
  control_owner?: RobotControlOwner;
  mapping_state?: RobotMappingState;
  active_map_id?: string | null;
  active_task_id?: string | null;
  active_map?: RobotMap | RobotMapSummary | null;
  current_pose?: RobotPose | null;
  target_pose?: RobotPose | null;
  active_task?: RobotNavigationTask | null;
  patrol_route?: RobotPatrolRoute | null;
  progress?: number;
  last_error?: RobotNavigationError | null;
  navigation_state?: string;
  current_task?: RobotTaskSummary | null;
  safety_interlock?: RobotSafetyInterlock | null;
  mock_scenario?: string;
  updated_at?: string;
  [key: string]: unknown;
}

export interface RobotStatusSnapshot extends MockRobotContract {
  gateway?: Record<string, unknown>;
  navigation?: RobotNavigationState;
  current_task?: RobotTaskSummary | null;
  safety_interlock?: RobotSafetyInterlock | null;
  control_owner?: RobotControlOwner;
  map?: RobotMapSummary | null;
  lidar?: RobotLidarDiagnostics;
  [key: string]: unknown;
}

export interface RobotDiagnostics extends RobotStatusSnapshot {
  checked_at?: string;
  error_code?: string | null;
  message?: string | null;
}

export interface LegacyRobotStatus {
  ok: boolean;
  gateway?: Record<string, unknown>;
  task_center?: {
    persisted: boolean;
    task_count: number;
    current_task?: RobotTaskSummary | null;
  };
  [key: string]: unknown;
}

export interface RobotStatusEvent extends MockRobotContract {
  type: string;
  sequence: number;
  timestamp: string;
  data: Record<string, unknown>;
  upstream_sequence?: number;
}

export interface RobotTimelineItem {
  id: string;
  type: string;
  title: string;
  message: string;
  timestamp: string;
  severity: "info" | "success" | "warning" | "error";
  code?: string;
}

export interface RobotContractIssue {
  code: "ROBOT_API_INVALID_ENVELOPE" | "ROBOT_INTERFACE_SAFETY_CONTRACT_VIOLATION";
  message: string;
  endpoint: string;
}

export type RobotMappingState =
  | "idle"
  | "mapping"
  | "preview_ready"
  | "saved"
  | "cancelled"
  | "failed";

export type RobotNavigationExecutionState =
  | "created"
  | "safety_checking"
  | "blocked"
  | "queued"
  | "navigating"
  | "paused_manual"
  | "paused_admin"
  | "arrived"
  | "voice_prompting"
  | "waiting_response"
  | "safe_response"
  | "help_requested"
  | "no_response"
  | "uncertain"
  | "waiting_admin_confirmation"
  | "returning_home"
  | "completed"
  | "failed"
  | "cancelled";

export type RobotMapStatus = "draft" | "preview" | "active" | "replaced" | "archived";
export type RobotMapPointType = "home" | "observation" | "patrol";
export type RobotMapPointStatus = "valid" | "invalid";
export type RobotPatrolRouteStatus = "draft" | "valid" | "active" | "invalid" | "archived";

export interface RobotPose {
  x: number;
  y: number;
  z?: number;
  yaw: number;
  source?: string;
}

export interface RobotNavigationError {
  code?: string;
  message?: string;
  blocked_by?: string[];
  [key: string]: unknown;
}

export interface RobotMap extends MockRobotContract {
  map_id: string;
  name: string;
  status: RobotMapStatus;
  revision: number;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  activated_at?: string | null;
  replaced_at?: string | null;
}

export interface RobotMapPoint extends MockRobotContract {
  point_id: string;
  map_id: string;
  name: string;
  point_type: RobotMapPointType;
  x: number;
  y: number;
  yaw: number;
  status: RobotMapPointStatus;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  invalidated_at?: string | null;
}

export interface RobotPatrolRoute extends MockRobotContract {
  route_id: string;
  map_id: string;
  name: string;
  status: RobotPatrolRouteStatus;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface RobotPatrolRoutePoint extends MockRobotContract {
  id?: number | null;
  route_id: string;
  point_id: string;
  sequence: number;
  metadata: Record<string, unknown>;
}

export interface RobotRouteDetail {
  route: RobotPatrolRoute;
  points: RobotPatrolRoutePoint[];
}

export interface RobotNavigationTask extends MockRobotContract {
  task_id: string;
  execution_state: RobotNavigationExecutionState;
  control_owner: RobotControlOwner;
  route_id?: string | null;
  map_id?: string | null;
  target_point_id?: string | null;
  progress?: number;
  safety_interlock?: RobotSafetyInterlock | null;
  updated_at?: string;
  [key: string]: unknown;
}

export interface RobotMapOperationResult {
  map: RobotMap;
  gateway: MockRobotContract & Record<string, unknown>;
}

export interface RobotMappingStartRequest {
  session_name: string;
  request_id: string;
}

export interface RobotMappingStopRequest {
  map_id: string;
  session_id: string;
  request_id: string;
}

export interface RobotMapPreviewRequest {
  map_id: string;
  metadata: Record<string, unknown>;
  request_id: string;
}

export interface RobotMapSaveRequest {
  map_id: string;
  session_id: string;
  name: string;
  replace_confirmed: boolean;
  request_id: string;
}

export interface RobotPointWriteRequest {
  point_id: string;
  map_id: string;
  name: string;
  point_type: RobotMapPointType;
  x: number;
  y: number;
  yaw: number;
  metadata: Record<string, unknown>;
  request_id: string;
}

export type RobotPointUpdateRequest = Partial<
  Pick<RobotPointWriteRequest, "name" | "point_type" | "x" | "y" | "yaw" | "metadata">
> & {
  request_id: string;
};

export interface RobotRouteWriteRequest {
  route_id: string;
  map_id: string;
  name: string;
  point_ids: string[];
  metadata: Record<string, unknown>;
  request_id: string;
}

export interface RobotPointCloudStreamInfo extends MockRobotContract {
  type: "point_cloud_stream_info";
  frame_id: string;
  coordinate_frame: string;
  encoding: string;
  target_fps: number;
  max_points: number;
  queue_size: number;
  scenario: string;
  stream_status: "ready" | "stale" | "error";
  timestamp: string;
}

export interface RobotPointCloudFrame extends MockRobotContract {
  type: "point_cloud_frame";
  sequence: number;
  timestamp: string;
  frame_id: string;
  coordinate_frame: string;
  scenario: string;
  point_count: number;
  points: Array<[number, number, number, number]>;
  robot_pose: Required<Pick<RobotPose, "x" | "y" | "z" | "yaw">>;
  target_pose: Required<Pick<RobotPose, "x" | "y" | "z" | "yaw">> | null;
  navigation_state: string;
  control_owner: RobotControlOwner;
}

export interface RobotPointCloudError extends MockRobotContract {
  type: "error";
  code: string;
  message: string;
  timestamp: string;
}

export type RobotDialogueIntent =
  | "safe_response"
  | "need_help"
  | "no_response"
  | "uncertain";

export type RobotEmergencyCaseStatus =
  | "open"
  | "blocked"
  | "active"
  | "escalated"
  | "resolved"
  | "cancelled";

export type RobotDialogueRole = "system" | "assistant" | "user";

export interface RobotEmergencyCase extends MockRobotContract {
  case_id: string;
  incident_id: string;
  robot_task_id: string | null;
  alarm_id: string | null;
  camera_id: string | null;
  area_id: string | null;
  area_name: string | null;
  observation_point_id: string | null;
  home_point_id: string | null;
  risk_level: string;
  fall_probability: number | null;
  status: RobotEmergencyCaseStatus;
  execution_state: RobotNavigationExecutionState;
  navigation_state: RobotNavigationExecutionState;
  control_owner: RobotControlOwner;
  dialogue_intent: RobotDialogueIntent | null;
  acknowledged_by: string | null;
  acknowledged_at: string | null;
  resolution: string | null;
  resolved_at: string | null;
  error_code: string | null;
  error_message: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface RobotDialogueTurn extends MockRobotContract {
  id: number | null;
  turn_id: string;
  incident_id: string;
  robot_task_id: string | null;
  role: RobotDialogueRole;
  text: string;
  input_text: string | null;
  intent: RobotDialogueIntent | null;
  confidence: number | null;
  recommended_action: string | null;
  reply_text: string | null;
  asr_status: string | null;
  tts_status: string | null;
  conversation_complete: boolean;
  metadata: Record<string, unknown>;
  occurred_at: string;
  created_at: string;
}

export interface RobotEmergencyEvent extends MockRobotContract {
  id: number | null;
  event_id: string;
  task_id: string | null;
  incident_id: string | null;
  event_type: string;
  execution_state: RobotNavigationExecutionState | null;
  navigation_state: RobotNavigationExecutionState | null;
  x: number | null;
  y: number | null;
  yaw: number | null;
  control_owner: RobotControlOwner;
  error_code: string | null;
  sequence: number;
  message: string;
  metadata: Record<string, unknown>;
  occurred_at: string;
  created_at: string;
}

export interface RobotEmergencyIncidentBundle extends MockRobotContract {
  incident_id: string;
  emergency_case: RobotEmergencyCase;
  robot_task_id: string | null;
  navigation_events: RobotEmergencyEvent[];
  dialogue_turns: RobotDialogueTurn[];
}

export interface RobotEmergencyWsMessage extends MockRobotContract {
  type: string;
  sequence: number;
  timestamp: string;
  data: RobotEmergencyIncidentBundle | RobotEmergencyCase;
  upstream_sequence?: number;
}

export interface RobotAlarmExtension {
  incident_id: string;
  robot_task_id?: string | null;
  alarm_id?: string | null;
  camera_id?: string | null;
  area_id?: string | null;
  area_name?: string | null;
  event_type?: string | null;
  occurred_at?: string | null;
  risk_level?: string | null;
  fall_probability?: number | null;
}

export interface RobotEmergencyDispatchRequest {
  request_id: string;
  area_id: string;
  area_name: string;
  alarm_id?: string;
  camera_id?: string;
  risk_level: string;
  fall_probability?: number;
}

export interface RobotEmergencyAcknowledgeRequest {
  request_id: string;
  admin_id: string;
}

export interface MockDialogueStartRequest {
  request_id: string;
  mock_prompt_text?: string;
}

export interface MockDialogueResultRequest {
  request_id: string;
  turn_id: string;
  intent: RobotDialogueIntent;
  input_text?: string;
  confidence?: number;
}

export interface RobotEmergencyResolveRequest {
  request_id: string;
  resolution: string;
}

export interface MockReturnCompleteRequest {
  request_id: string;
}
