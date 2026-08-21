export interface DeviceRecord {
  id?: string;
  mac_address: string;
  device_name: string;
  model_code?: string;
  ingest_mode?: "serial" | "mqtt" | "ble" | "mock";
  service_uuid?: string;
  device_uuid?: string;
  user_id?: string | null;
  status: string;
  activation_state?: "pending" | "active";
  bind_status?: "unbound" | "bound" | "disabled";
  last_seen_at?: string | null;
  last_packet_type?: string | null;
  created_at?: string;
}

export interface DeviceBindLogRecord {
  id: string;
  device_id: string;
  old_user_id?: string | null;
  new_user_id?: string | null;
  action_type: string;
  operator_id?: string | null;
  reason?: string | null;
  created_at: string;
}

export interface HealthSample {
  device_mac: string;
  timestamp: string;
  heart_rate: number;
  temperature: number;
  blood_oxygen: number;
  source?: "serial" | "mock" | "mqtt" | "ble";
  ambient_temperature?: number | null;
  surface_temperature?: number | null;
  blood_pressure?: string;
  battery?: number;
  steps?: number | null;
  device_uuid?: string | null;
  packet_type?: string | null;
  sos_flag?: boolean;
  sos_value?: number | null;
  sos_trigger?: "double_click" | "long_press" | null;
  health_score?: number | null;
}

export interface AlarmRecord {
  id: string;
  device_mac: string;
  alarm_type: string;
  alarm_level: number;
  alarm_layer: string;
  message: string;
  acknowledged: boolean;
  created_at: string;
  anomaly_probability?: number | null;
  metadata?: Record<string, unknown>;
}

export interface AlarmQueueItem {
  score: number;
  alarm: AlarmRecord;
}

export interface MobilePushRecord {
  id: string;
  alarm_id: string;
  device_mac: string;
  title: string;
  body: string;
  priority: number;
  created_at: string;
  delivered: boolean;
}

export interface AgentResponse {
  answer: string;
  references: string[];
  analysis?: Record<string, unknown>;
  attachments?: AgentAttachment[];
  citations?: AgentCitation[];
  artifact_ids?: string[];
  scope?: AnalysisScope | "device";
  window?: WindowKind;
  subject?: Record<string, unknown> | null;
  mode?: string;
  selected_provider?: string;
  selected_model?: string;
  degraded?: string[];
}

export type CommunityWorkflow =
  | "overview"
  | "risk_ranking"
  | "alert_digest"
  | "device_focus"
  | "elder_focus"
  | "community_report"
  | "elder_report"
  | "report_generation"
  | "free_chat";
export type AgentAttachmentRenderType = "metric_cards" | "table" | "echarts" | "report_document";
export type AnalysisScope = "elder" | "community";
export type AgentProvider = "qwen" | "tongyi" | "ollama" | "auto";

export interface AgentAttachment {
  id: string;
  title: string;
  summary?: string;
  render_type: AgentAttachmentRenderType;
  render_payload: Record<string, unknown>;
  source_tool?: string;
}

export interface AgentCitation {
  id: string;
  title: string;
  source_path: string;
  chunk_id: string;
  snippet: string;
  score: number;
}

export interface AgentElderSubject {
  elder_id: string;
  elder_name: string;
  apartment: string;
  device_macs: string[];
  has_realtime_device: boolean;
  latest_timestamp?: string | null;
  risk_level: string;
  is_demo_subject: boolean;
}

export interface CommunityAnalysisPayload {
  question: string;
  role: string;
  mode: string;
  history_minutes?: number;
  per_device_limit?: number;
  device_macs?: string[];
  workflow?: CommunityWorkflow;
  focus_device_mac?: string;
  history?: Array<{
    role: "user" | "assistant";
    content: string;
  }>;
  scope?: AnalysisScope;
  subject_elder_id?: string | null;
  window?: WindowKind;
  provider?: AgentProvider;
  include_report?: boolean;
}

export type AgentStreamEventType =
  | "session.started"
  | "stage.changed"
  | "trace.note"
  | "tool.started"
  | "tool.finished"
  | "answer.delta"
  | "answer.completed"
  | "session.completed"
  | "session.error";

export interface AgentStreamEventBase {
  type: AgentStreamEventType;
  timestamp?: string;
}

export interface AgentSessionStartedEvent extends AgentStreamEventBase {
  type: "session.started";
  session_id: string;
  scope: string;
  selected_model?: string;
  degraded_notes?: string[];
}

export interface AgentStageEvent extends AgentStreamEventBase {
  type: "stage.changed";
  stage: string;
  status: "running" | "completed" | "error";
  label?: string;
  detail?: string;
  summary?: string;
  elapsed_ms?: number | null;
  group?: "trace";
}

export interface AgentTraceEvent extends AgentStreamEventBase {
  type: "trace.note";
  stage: string;
  note: string;
  level?: "info" | "warning" | "error";
}

export interface AgentToolEvent extends AgentStreamEventBase {
  type: "tool.started" | "tool.finished";
  stage: string;
  tool_name: string;
  request_id: string;
  source?: string;
  status?: string;
  success?: boolean;
  summary?: string;
  error_message?: string | null;
  title?: string;
  tool_kind?: "data_query" | "analysis" | "report" | "recommendation";
  input_preview?: string;
  output_preview?: string;
  child_tools?: Array<{
    name: string;
    title?: string;
    summary?: string;
    status?: string;
  }>;
  render_type?: AgentAttachmentRenderType;
  render_payload?: Record<string, unknown>;
  attachments?: AgentAttachment[];
}

export interface AgentAnswerDeltaEvent extends AgentStreamEventBase {
  type: "answer.delta";
  session_id: string;
  delta: string;
}

export interface AgentAnswerCompletedEvent extends AgentStreamEventBase {
  type: "answer.completed";
  session_id: string;
  answer: string;
  references?: string[];
  analysis?: Record<string, unknown>;
  attachments?: AgentAttachment[];
  citations?: AgentCitation[];
  artifact_ids?: string[];
  scope?: AnalysisScope;
  window?: WindowKind;
  subject?: Record<string, unknown> | null;
}

export interface AgentSessionCompletedEvent extends AgentStreamEventBase {
  type: "session.completed";
  session_id: string;
  selected_model?: string;
  degraded_notes?: string[];
}

export interface AgentSessionErrorEvent extends AgentStreamEventBase {
  type: "session.error";
  session_id?: string;
  error: string;
}

export type AgentStreamEvent =
  | AgentSessionStartedEvent
  | AgentStageEvent
  | AgentTraceEvent
  | AgentToolEvent
  | AgentAnswerDeltaEvent
  | AgentAnswerCompletedEvent
  | AgentSessionCompletedEvent
  | AgentSessionErrorEvent;

export interface AgentReportPeriod {
  start_at: string;
  end_at: string;
  duration_minutes: number;
  sample_count: number;
}

export interface AgentMetricReportItem {
  latest?: number | null;
  average?: number | null;
  min?: number | null;
  max?: number | null;
  trend?: string | null;
}

export interface AgentDeviceHealthReport {
  report_type: "device_health_report";
  device_mac: string;
  subject_name?: string | null;
  device_name?: string | null;
  generated_at: string;
  period: AgentReportPeriod;
  summary: string;
  risk_level: string;
  risk_flags: string[];
  key_findings: string[];
  recommendations: string[];
  metrics: Record<string, AgentMetricReportItem>;
  references: string[];
}

export interface CommunityOverview {
  clusters: Record<string, string[]>;
  device_count: number;
  intelligent_anomaly_score: number;
  trend?: Record<string, number>;
  risk_heatmap?: Array<Record<string, unknown>>;
}

export interface IntelligentDeviceAnalysis {
  device_mac: string;
  ready: boolean;
  probability?: number;
  score?: number;
  drift_score?: number;
  reconstruction_score?: number;
  reason?: string;
  message?: string;
}

export interface CommunityProfile {
  id: string;
  name: string;
  address: string;
  manager: string;
  hotline: string;
}

export interface ElderProfile {
  id: string;
  name: string;
  age: number;
  apartment: string;
  community_id: string;
  device_mac: string;
  device_macs?: string[];
  family_ids: string[];
}

export interface FamilyProfile {
  id: string;
  name: string;
  relationship: string;
  phone: string;
  community_id: string;
  elder_ids: string[];
  login_username: string;
}

export interface CareDirectory {
  community: CommunityProfile;
  elders: ElderProfile[];
  families: FamilyProfile[];
}

export interface Go2CompanionHealthContext {
  risk_level: "low" | "medium" | "high" | "unknown";
  health_score: number | null;
  recent_fall: boolean;
  sos: boolean;
  today_steps: number | null;
  data_freshness: "fresh" | "stale" | "missing";
  device_mac: string | null;
}

export interface Go2CompanionEnvironmentContext {
  weather: "sunny" | "rain" | "windy" | "hot" | "cold" | "unknown";
  temperature: number | null;
  humidity: number | null;
  wind_level: number | null;
  description: string;
  suggestion: string;
  provider: "mock" | "qweather";
  source: "mock" | "qweather";
}

export interface Go2CompanionContext {
  elder_id: string;
  elder_name: string;
  generated_at: string;
  health: Go2CompanionHealthContext;
  environment: Go2CompanionEnvironmentContext;
  location: {
    city: string;
    area: string;
    address: string;
    provider: "mock";
  };
  robot: {
    online: boolean;
    motion_enabled: false;
    provider: "mock";
  };
}

export interface Go2CompanionHealthMetrics {
  available: boolean;
  source: "realtime_stream";
  observed_at: string | null;
  freshness: "fresh" | "stale" | "missing";
  risk_level: "low" | "medium" | "high" | "unknown";
  heart_rate: number | null;
  blood_oxygen: number | null;
  temperature: number | null;
  blood_pressure: string | null;
  health_score: number | null;
  steps: number | null;
  recent_fall: boolean;
  sos: boolean;
}

export interface Go2CompanionTextTurnRequest {
  elder_id: string;
  text: string;
  session_id?: string;
  device_mac?: string;
  location_hint?: string;
}

export interface Go2CompanionTextTurnResponse {
  agent: "go2_companion";
  version: "1.1";
  session_id: string;
  reply: string;
  llm_provider: string;
  llm_model: string;
  context: Go2CompanionContext;
  health_metrics: Go2CompanionHealthMetrics;
}

export interface Go2CompanionVoiceTurnResponse {
  agent: "go2_companion";
  version: "1.0";
  session_id: string;
  transcript: string;
  reply: string;
  audio_b64: string;
  audio_url: string;
  audio_format: string;
  asr_provider: string;
  llm_provider: string;
  llm_model: string;
  tts_provider: string;
  tts_voice: string;
  grounded: boolean;
  context: Go2CompanionContext | null;
  health_metrics: Go2CompanionHealthMetrics | null;
  playback: {
    mode: "response_only";
    go2_status: "not_configured";
    ready_for_client_playback: boolean;
    message: string;
  };
}

export interface Go2CompanionStatus {
  pipeline: string[];
  asr_configured: boolean;
  llm_configured: boolean;
  tts_configured: boolean;
  asr_model: string;
  llm_model: string;
  tts_model: string;
  playback_mode: "response_only";
  go2_microphone: "not_configured";
  go2_speaker: "not_configured";
  context_grounding_supported: boolean;
}

export interface SessionUser {
  id: string;
  username: string;
  name: string;
  role: "family" | "community" | "admin" | "elder";
  community_id: string;
  family_id?: string | null;
}

export interface AuthAccountPreview {
  username: string;
  display_name: string;
  role: "family" | "community" | "admin" | "elder";
  family_id?: string | null;
  community_id: string;
  default_password: string;
}

export interface LoginResponse {
  token: string;
  user: SessionUser;
  expires_at: string;
}

export interface ElderRegisterRequest {
  name: string;
  phone: string;
  password: string;
  age: number;
  apartment: string;
  community_id?: string;
}

export interface FamilyRegisterRequest {
  name: string;
  phone: string;
  password: string;
  relationship: string;
  community_id?: string;
  login_username?: string | null;
}

export interface CommunityRegisterRequest {
  name: string;
  phone: string;
  password: string;
  community_id?: string;
  login_username?: string | null;
}

export interface UserRegisterResponse {
  id: string;
  name: string;
  role: "family" | "community" | "admin" | "elder";
  phone: string;
  created_at: string;
}

export interface CareFeatureAccess {
  basic_advice: boolean;
  device_metrics: boolean;
  health_evaluation: boolean;
  health_report: boolean;
}

export interface CareAccessDeviceMetric {
  device_mac: string;
  device_name: string;
  device_status: string;
  bind_status: string;
  elder_id?: string | null;
  elder_name?: string | null;
  latest_sample?: HealthSample | null;
}

export interface CareHealthReportSummary {
  device_mac: string;
  risk_level: string;
  sample_count: number;
  latest_health_score?: number | null;
  recommendations: string[];
  notable_events: string[];
}

export interface CareHealthEvaluationSummary {
  device_mac: string;
  risk_level: string;
  risk_flags: string[];
  latest_health_score?: number | null;
}

export interface CareAccessProfile {
  user_id: string;
  role: "family" | "community" | "admin" | "elder";
  community_id: string;
  family_id?: string | null;
  binding_state: "bound" | "unbound" | "not_applicable";
  bound_device_macs: string[];
  related_elder_ids: string[];
  capabilities: CareFeatureAccess;
  basic_advice: string;
  device_metrics: CareAccessDeviceMetric[];
  health_evaluations: CareHealthEvaluationSummary[];
  health_reports: CareHealthReportSummary[];
}

export interface CommunityDashboardMetrics {
  elder_count: number;
  family_count: number;
  device_total: number;
  device_pending: number;
  device_online: number;
  device_offline: number;
  active_alarm_count: number;
  unacknowledged_alarm_count: number;
  sos_alarm_count: number;
  health_alert_count: number;
  device_alert_count: number;
  high_risk_elder_count: number;
  average_health_score: number;
  average_blood_oxygen: number;
  today_alarm_count: number;
  last_sync_at?: string | null;
}

export interface CommunityDashboardTrendPoint {
  timestamp: string;
  average_health_score: number;
  alert_count: number;
  high_risk_count: number;
}

export interface StructuredHealthInsight {
  evaluated_at?: string | null;
  health_score?: number | null;
  rule_health_score?: number | null;
  model_health_score?: number | null;
  risk_level?: string | null;
  abnormal_tags: string[];
  trigger_reasons: string[];
  active_event_count: number;
  recommendation_code?: string | null;
  score_adjustment_reason?: string | null;
}

export interface CommunityDashboardElderItem {
  elder_id: string;
  elder_name: string;
  apartment: string;
  device_mac?: string | null;
  family_names: string[];
  risk_level: "high" | "medium" | "low";
  risk_score: number;
  risk_reasons: string[];
  device_status: string;
  latest_timestamp?: string | null;
  latest_health_score?: number | null;
  heart_rate?: number | null;
  blood_oxygen?: number | null;
  blood_pressure?: string | null;
  temperature?: number | null;
  active_alarm_count: number;
  sos_active?: boolean;
  active_sos_alarm_id?: string | null;
  active_sos_trigger?: "double_click" | "long_press" | null;
  structured_health?: StructuredHealthInsight | null;
}

export interface CommunityDashboardDeviceItem {
  device_mac: string;
  device_name: string;
  model_code?: string | null;
  ingest_mode?: string | null;
  service_uuid?: string | null;
  device_uuid?: string | null;
  elder_id?: string | null;
  elder_name?: string | null;
  apartment?: string | null;
  device_status: string;
  activation_state?: string | null;
  bind_status: string;
  risk_level: "high" | "medium" | "low";
  risk_reasons: string[];
  latest_timestamp?: string | null;
  last_seen_at?: string | null;
  last_packet_type?: string | null;
  latest_health_score?: number | null;
  heart_rate?: number | null;
  blood_oxygen?: number | null;
  blood_pressure?: string | null;
  temperature?: number | null;
  battery?: number | null;
  steps?: number | null;
  active_alarm_count: number;
  sos_active?: boolean;
  active_sos_alarm_id?: string | null;
  active_sos_trigger?: "double_click" | "long_press" | null;
  structured_health?: StructuredHealthInsight | null;
}

export interface CommunityDashboardAlertItem {
  alarm_id: string;
  device_mac: string;
  elder_name?: string | null;
  apartment?: string | null;
  alarm_type: string;
  alarm_layer: string;
  alarm_level: number;
  message: string;
  created_at: string;
  acknowledged: boolean;
}

export interface RelationTopologyNode {
  id: string;
  kind: "community" | "elder" | "family" | "device";
  label: string;
  subtitle?: string | null;
  status?: string | null;
  risk_level?: string | null;
}

export interface RelationTopologyLane {
  elder: RelationTopologyNode;
  families: RelationTopologyNode[];
  devices: RelationTopologyNode[];
}

export interface CommunityRelationTopology {
  community: RelationTopologyNode;
  lanes: RelationTopologyLane[];
  unassigned_devices: RelationTopologyNode[];
}

export interface CommunityDashboardSummary {
  community: CommunityProfile;
  metrics: CommunityDashboardMetrics;
  top_risk_elders: CommunityDashboardElderItem[];
  device_statuses: CommunityDashboardDeviceItem[];
  recent_alerts: CommunityDashboardAlertItem[];
  trend: CommunityDashboardTrendPoint[];
  relation_topology?: CommunityRelationTopology | null;
}

export interface SystemInfoResponse {
  runtime_mode?: "mock" | "serial" | "mqtt";
  bootstrap_source?: string;
  bootstrap_status?: string;
  bootstrap_reason?: string;
  competition_stack: Record<string, unknown>;
  configured: Record<string, unknown>;
  serial_runtime?: {
    enabled: boolean;
    port: string;
    baudrate: number;
    collection_strategy?: string;
    packet_type: number;
    mac_filter: string;
    auto_configure: boolean;
    broadcast_sos_overlay: boolean;
    response_cycle_seconds: number;
    broadcast_cycle_seconds: number;
    active_target_mac?: string | null;
    active_target_device_name?: string | null;
    target_locked?: boolean;
    merge_mode?: string;
    runtime_mode?: string;
    bootstrap_source?: string;
    bootstrap_status?: string;
    bootstrap_reason?: string;
  };
  demo_data?: DemoDataStatus;
}

export interface DemoDataStatus {
  enabled: boolean;
  device_count: number;
  subject_count: number;
  latest_sample_at?: string | null;
  seed_profiles: string[];
}

export interface SerialTargetSwitchResponse {
  active_target_mac?: string | null;
  active_target_device_name?: string | null;
  previous_target_mac?: string | null;
  switched_at: string;
}

export interface ChatProviderCapability {
  chat_configured?: boolean;
  configured?: boolean;
  chat_model?: string;
  embedding_model?: string;
  rerank_model?: string;
  base_url?: string;
  model?: string;
}

export interface ChatRetrievalCapability {
  retrieval_mode: string;
  document_count: number;
  chunk_count: number;
  docs_hash: string;
  vector_enabled: boolean;
  bm25_enabled: boolean;
  rerank_enabled: boolean;
  embedding_model?: string;
  rerank_model?: string;
}

export interface AgentToolSpec {
  name: string;
  description: string;
  source?: string;
}

export interface ChatCapabilities {
  runtime: string;
  providers: {
    tongyi: ChatProviderCapability;
    ollama: ChatProviderCapability;
  };
  retrieval: ChatRetrievalCapability;
  analysis_tools: string[];
  tool_specs: AgentToolSpec[];
  extensions: {
    mcp_connected: boolean;
    demo_data?: DemoDataStatus;
  };
}

export type WindowKind = "day" | "week";
export type HistoryBucket = "raw" | "hour" | "day";

export interface SensorHistoryPoint {
  bucket_start: string;
  bucket_end?: string | null;
  heart_rate?: number | null;
  temperature?: number | null;
  blood_oxygen?: number | null;
  health_score?: number | null;
  battery?: number | null;
  steps?: number | null;
  sos_count: number;
  sample_count: number;
  risk_level?: string | null;
}

export interface DeviceHistoryResponse {
  device_mac: string;
  window: WindowKind;
  bucket: HistoryBucket;
  points: SensorHistoryPoint[];
}

export interface ChartPayload {
  id: string;
  title: string;
  type: string;
  echarts_option: Record<string, unknown>;
  summary: string;
}

export interface HighRiskEntity {
  device_mac: string;
  elder_name?: string | null;
  risk_level: string;
  latest_health_score?: number | null;
  active_alert_count: number;
  reasons: string[];
}

export interface CommunityWindowAnalysis {
  key_metrics: Record<string, unknown>;
  risk_distribution: Record<string, number>;
  alert_breakdown: Record<string, number>;
  device_status_distribution: Record<string, number>;
  high_risk_entities: HighRiskEntity[];
  trend_findings: string[];
  chart_payloads: ChartPayload[];
}

export interface CommunityWindowReportResponse {
  window: WindowKind;
  generated_at: string;
  analysis: CommunityWindowAnalysis;
}

export interface AgentSourceItem {
  source_type: string;
  title: string;
  url?: string | null;
  snippet: string;
}

export interface CommunityAgentMeta {
  llm_model: string;
  embedding_model: string;
  rerank_model: string;
  used_tavily: boolean;
  used_rerank: boolean;
  degraded_notes: string[];
}

export interface CommunityAgentSummaryResponse {
  window: WindowKind;
  generated_at: string;
  summary_text: string;
  advice: string[];
  analysis: CommunityWindowAnalysis;
  charts: ChartPayload[];
  sources: AgentSourceItem[];
  agent_meta: CommunityAgentMeta;
}

export interface HealthScoreInsightRequest {
  device_mac: string;
  elder_id?: string | null;
  window_minutes?: number;
  use_llm?: boolean;
}

export interface HealthScoreInsightResponse {
  elder_name?: string | null;
  room_no?: string | null;
  device_mac: string;
  generated_at: string;
  data_freshness: "fresh" | "stale" | "missing";
  risk_level: "low" | "medium" | "high" | "critical";
  summary: string;
  score_explanation: string;
  trend_analysis: string;
  model_assessment: string;
  suggested_actions: string[];
  watch_items: string[];
  confidence: "low" | "medium" | "high";
  llm_used: boolean;
  fallback_used: boolean;
}
 
export interface FamilyRelationCreateRequest {
  elder_user_id: string;
  family_user_id: string;
  relation_type: string;
  is_primary?: boolean;
}

export interface FamilyRelationRecord {
  id: string;
  elder_user_id: string;
  family_user_id: string;
  relation_type: string;
  is_primary: boolean;
  status: string;
  created_at: string;
}

export interface VisionHealthResponse {
  status?: string;
  reason?: string;
  base_url?: string;
  camera_id?: string;
  default_camera_id?: string;
  vision_service?: Record<string, unknown> | null;
  [key: string]: unknown;
}

export type RobotTaskStatus = "QUEUED" | "RUNNING" | "COMPLETED" | "FAILED" | "CANCELLED" | "BLOCKED";
export type RobotTaskStep =
  | "RECEIVED"
  | "PREFLIGHT"
  | "MOVING"
  | "ARRIVED"
  | "CAMERA_CHECK"
  | "VOICE_PROMPT"
  | "WAITING_RESPONSE"
  | "REPORTING";
export type RobotTaskOutcome = "SAFE" | "NEED_HELP" | "NO_RESPONSE" | "UNKNOWN";

export interface RobotTask {
  task_id: string;
  gateway_task_id?: string | null;
  source_event_id: string;
  trace_id: string;
  alarm_event_id?: string | null;
  elder_id: string;
  elder_name: string;
  robot_id?: string | null;
  task_type: string;
  location: string;
  risk_level: string;
  status: RobotTaskStatus;
  current_step: RobotTaskStep;
  outcome?: RobotTaskOutcome | null;
  last_sequence: number;
  error_code?: string | null;
  error_message?: string | null;
  created_at: string;
  started_at?: string | null;
  completed_at?: string | null;
  updated_at: string;
}

export interface RobotTaskTimeline {
  id?: number | null;
  task_id: string;
  callback_id?: string | null;
  sequence: number;
  status: RobotTaskStatus;
  step: RobotTaskStep;
  message: string;
  occurred_at: string;
  payload: Record<string, unknown>;
  created_at: string;
}

export interface RobotObservation {
  id?: number | null;
  task_id: string;
  snapshot_url?: string | null;
  camera_available?: boolean | null;
  voice_available?: boolean | null;
  response_type?: RobotTaskOutcome | null;
  transcript?: string | null;
  observed_at: string;
  raw_payload: Record<string, unknown>;
}

export interface RobotTaskListResponse {
  tasks: RobotTask[];
}

export interface RobotTaskDetailResponse {
  task: RobotTask;
  gateway?: Record<string, unknown> | null;
}

export interface RobotTaskTimelineResponse {
  timeline: RobotTaskTimeline[];
}

export interface RobotTaskObservationResponse {
  observation?: RobotObservation | null;
}

export interface RobotStatusResponse {
  ok: boolean;
  gateway?: Record<string, unknown>;
  task_center?: {
    persisted: boolean;
    task_count: number;
    current_task?: RobotTask | null;
  };
}

export interface RobotSocketEvent {
  event_type?: string;
  task_id?: string;
  gateway_task_id?: string | null;
  source_event_id?: string;
  trace_id?: string;
  status?: RobotTaskStatus;
  step?: RobotTaskStep;
  outcome?: RobotTaskOutcome | null;
  occurred_at?: string;
}

export const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000/api/v1";
export const WS_BASE = (import.meta.env.VITE_WS_BASE ?? "ws://localhost:8000").replace(/\/$/, "");

export function getMainSystemBaseUrl(): string {
  try {
    return new URL(API_BASE, window.location.origin).origin;
  } catch {
    return window.location.origin;
  }
}

export function getVisionHealthEndpoint(): string {
  return `${API_BASE}/vision/health`;
}

export class ApiError extends Error {
  status: number;
  detail: string;
  code?: string;
  data?: Record<string, unknown>;

  constructor(status: number, detail: string, code?: string, data?: Record<string, unknown>) {
    super(detail || `Request failed: ${status}`);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail || `Request failed: ${status}`;
    this.code = code;
    this.data = data;
  }
}

function humanizeApiDetail(detail: string): string {
  if (detail.includes("INVALID_MAC_ADDRESS")) return "设备 MAC 格式错误，请使用 AA:BB:CC:DD:EE:FF。";
  if (detail.includes("INVALID_MAC_PREFIX")) return "当前服务尚未完成更新，请刷新页面或重启后端后重试。";
  if (detail.includes("DEVICE_ALREADY_EXISTS")) return "该设备已经登记在台账中。";
  if (detail.includes("TARGET_USER_ALREADY_HAS_DEVICE_OF_SAME_MODEL")) {
    return "该老人已经绑定了同型号手环。若本次只是演示新设备，请选择“暂不绑定，先登记设备”。";
  }
  return detail;
}

export async function requestJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  if (!response.ok) {
    let detail = `Request failed: ${response.status}`;
    let code: string | undefined;
    let errorData: Record<string, unknown> | undefined;
    try {
      const payload = (await response.json()) as {
        code?: string;
        message?: string;
        data?: Record<string, unknown>;
        detail?:
          | string
          | { message?: string; code?: string }
          | Array<{ msg?: string; loc?: Array<string | number> }>;
      };
      if (typeof payload.code === "string") code = payload.code;
      if (typeof payload.message === "string" && payload.message) detail = payload.message;
      if (payload.data && typeof payload.data === "object" && !Array.isArray(payload.data)) {
        errorData = payload.data;
      }
      const detailPayload = payload.detail;
      if (typeof detailPayload === "string") {
        detail = humanizeApiDetail(detailPayload);
      } else if (Array.isArray(detailPayload) && detailPayload.length) {
        const first = detailPayload[0];
        const message = String(first.msg ?? "");
        if (message.includes("INVALID_MAC_ADDRESS")) detail = "设备 MAC 格式错误，请使用 AA:BB:CC:DD:EE:FF。";
        else if (message.includes("question")) detail = "请输入更具体的问题后再试。";
        else if (message.includes("mode")) detail = "请求模式无效，请联系开发人员检查前端参数。";
        else if (message.includes("role")) detail = "请求角色无效，请联系开发人员检查前端参数。";
        else detail = message.replace(/^Value error,\s*/i, "") || detail;
      } else if (detailPayload && !Array.isArray(detailPayload) && detailPayload.message) {
        detail = detailPayload.message;
      } else if (detailPayload && !Array.isArray(detailPayload) && detailPayload.code) {
        code = detailPayload.code;
        detail = detailPayload.code;
      }
    } catch {
      // ignore non-json error bodies
    }
    throw new ApiError(response.status, detail, code, errorData);
  }
  return (await response.json()) as T;
}

function withBearer(token?: string): HeadersInit | undefined {
  if (!token) return undefined;
  return { Authorization: `Bearer ${token}` };
}

function jsonHeaders(token?: string): HeadersInit {
  return {
    "Content-Type": "application/json",
    ...(withBearer(token) ?? {}),
  };
}

async function throwApiError(response: Response): Promise<never> {
  let detail = `Request failed: ${response.status}`;
  try {
    const payload = (await response.json()) as {
      detail?: string | { message?: string; code?: string };
    };
    if (typeof payload.detail === "string") {
      detail = humanizeApiDetail(payload.detail);
    } else if (payload.detail?.message) {
      detail = humanizeApiDetail(payload.detail.message);
    } else if (payload.detail?.code) {
      detail = humanizeApiDetail(payload.detail.code);
    }
  } catch {
    // ignore non-json errors
  }
  throw new ApiError(response.status, detail);
}

export async function streamCommunityAnalysis(
  payload: CommunityAnalysisPayload,
  handlers: {
    signal?: AbortSignal;
    onEvent?: (event: AgentStreamEvent) => void;
  } = {},
): Promise<void> {
  const response = await fetch(`${API_BASE}/chat/analyze/community/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    signal: handlers.signal,
  });

  if (!response.ok) {
    await throwApiError(response);
  }

  if (!response.body) {
    throw new ApiError(500, "Stream body is not available");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";

  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const chunks = buffer.split("\n");
      buffer = chunks.pop() ?? "";

      for (const line of chunks) {
        const trimmed = line.trim();
        if (!trimmed) continue;
        const event = JSON.parse(trimmed) as AgentStreamEvent;
        handlers.onEvent?.(event);
      }
    }

    const tail = `${buffer}${decoder.decode()}`.trim();
    if (tail) {
      handlers.onEvent?.(JSON.parse(tail) as AgentStreamEvent);
    }
  } finally {
    reader.releaseLock();
  }
}

export const api = {
  listDevices: () => requestJson<DeviceRecord[]>(`${API_BASE}/devices`),
  getDevice: (mac: string) => requestJson<DeviceRecord>(`${API_BASE}/devices/${mac}`),
  registerDevice: (
    payload: {
      mac_address: string;
      device_name?: string;
      user_id?: string | null;
      model_code?: string;
      ingest_mode?: "serial" | "mqtt" | "ble" | "mock";
      service_uuid?: string;
      device_uuid?: string;
    },
    token?: string,
  ) =>
    requestJson<DeviceRecord>(`${API_BASE}/devices/register`, {
      method: "POST",
      headers: jsonHeaders(token),
      body: JSON.stringify(payload),
    }),
  bindDevice: (payload: { mac_address: string; target_user_id: string; operator_id?: string | null }, token?: string) =>
    requestJson<DeviceBindLogRecord>(`${API_BASE}/devices/bind`, {
      method: "POST",
      headers: jsonHeaders(token),
      body: JSON.stringify(payload),
    }),
  unbindDevice: (payload: { mac_address: string; operator_id?: string | null; reason?: string | null }, token?: string) =>
    requestJson<DeviceBindLogRecord>(`${API_BASE}/devices/unbind`, {
      method: "POST",
      headers: jsonHeaders(token),
      body: JSON.stringify(payload),
    }),
  rebindDevice: (payload: {
    mac_address: string;
    new_user_id: string;
    operator_id?: string | null;
    reason?: string | null;
  }, token?: string) =>
    requestJson<DeviceBindLogRecord>(`${API_BASE}/devices/rebind`, {
      method: "POST",
      headers: jsonHeaders(token),
      body: JSON.stringify(payload),
    }),
  deleteDevice: (mac: string, token?: string) =>
    requestJson<DeviceRecord>(`${API_BASE}/devices/${mac}`, {
      method: "DELETE",
      headers: withBearer(token),
    }),
  switchSerialTarget: (payload: { mac_address: string }, token?: string) =>
    requestJson<SerialTargetSwitchResponse>(`${API_BASE}/devices/serial-target`, {
      method: "POST",
      headers: jsonHeaders(token),
      body: JSON.stringify(payload),
    }),
  listDeviceBindLogs: (mac: string) =>
    requestJson<DeviceBindLogRecord[]>(`${API_BASE}/devices/${mac}/bind-logs`),
  registerElder: (payload: ElderRegisterRequest, token?: string) =>
    requestJson<UserRegisterResponse>(`${API_BASE}/users/elders/register`, {
      method: "POST",
      headers: jsonHeaders(token),
      body: JSON.stringify(payload),
    }),
  registerFamily: (payload: FamilyRegisterRequest, token?: string) =>
    requestJson<UserRegisterResponse>(`${API_BASE}/users/families/register`, {
      method: "POST",
      headers: jsonHeaders(token),
      body: JSON.stringify(payload),
    }),
  bindFamilyRelation: (payload: FamilyRelationCreateRequest, token?: string) =>
    requestJson<FamilyRelationRecord>(`${API_BASE}/relations/family-bind`, {
      method: "POST",
      headers: jsonHeaders(token),
      body: JSON.stringify(payload),
    }),
  getRealtime: (mac: string) => requestJson<HealthSample>(`${API_BASE}/health/realtime/${mac}`),
  getTrend: (mac: string, minutes = 180, limit = 120) =>
    requestJson<HealthSample[]>(`${API_BASE}/health/trend/${mac}?minutes=${minutes}&limit=${limit}`),
  getCommunityOverview: () =>
    requestJson<CommunityOverview>(`${API_BASE}/health/community/overview`),
  getIntelligentAnalysis: (mac: string) =>
    requestJson<IntelligentDeviceAnalysis>(`${API_BASE}/health/intelligent/${mac}`),
  listAlarms: () => requestJson<AlarmRecord[]>(`${API_BASE}/alarms?active_only=true`),
  listAlarmQueue: () => requestJson<AlarmQueueItem[]>(`${API_BASE}/alarms/queue`),
  listMobilePushes: (limit = 10) =>
    requestJson<MobilePushRecord[]>(`${API_BASE}/alarms/mobile-pushes?limit=${limit}`),
  ackAlarm: (alarmId: string) =>
    requestJson<AlarmRecord>(`${API_BASE}/alarms/${alarmId}/acknowledge`, { method: "POST" }),
  analyze: (payload: {
    device_mac: string;
    question: string;
    role: string;
    mode: string;
    history_limit?: number;
    history_minutes?: number;
  }) =>
    requestJson<AgentResponse>(`${API_BASE}/chat/analyze`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  analyzeCommunity: (payload: CommunityAnalysisPayload) =>
    requestJson<AgentResponse>(`${API_BASE}/chat/analyze/community`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  generateDeviceHealthReport: (payload: {
    device_mac: string;
    start_at: string;
    end_at: string;
    role?: string;
    mode?: string;
  }) =>
    requestJson<AgentDeviceHealthReport>(`${API_BASE}/chat/report/device`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  getCareDirectory: () => requestJson<CareDirectory>(`${API_BASE}/care/directory`),
  getGo2CompanionStatus: () =>
    requestJson<Go2CompanionStatus>(`${API_BASE}/go2-companion/status`),
  runGo2CompanionTextTurn: (payload: Go2CompanionTextTurnRequest) =>
    requestJson<Go2CompanionTextTurnResponse>(`${API_BASE}/go2-companion/text-turn`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  runGo2CompanionVoiceTurn: (payload: {
    file: File;
    session_id: string;
    voice?: string;
    elder_id?: string;
    device_mac?: string;
    location_hint?: string;
  }) => {
    const form = new FormData();
    form.append("file", payload.file, payload.file.name);
    form.append("session_id", payload.session_id);
    form.append("voice", payload.voice ?? "Serena");
    if (payload.elder_id) form.append("elder_id", payload.elder_id);
    if (payload.device_mac) form.append("device_mac", payload.device_mac);
    if (payload.location_hint) form.append("location_hint", payload.location_hint);
    return requestJson<Go2CompanionVoiceTurnResponse>(`${API_BASE}/go2-companion/voice-turn`, {
      method: "POST",
      body: form,
    });
  },
  getFamilyCareDirectory: (familyId: string) =>
    requestJson<CareDirectory>(`${API_BASE}/care/directory/family/${familyId}`),
  listMockAccounts: () => requestJson<AuthAccountPreview[]>(`${API_BASE}/auth/mock-accounts`),
  login: (payload: { username: string; password: string }) =>
    requestJson<LoginResponse>(`${API_BASE}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  loginMock: (payload: { username: string; password: string }) =>
    requestJson<LoginResponse>(`${API_BASE}/auth/mock-login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  publicRegisterElder: (payload: ElderRegisterRequest) =>
    requestJson<UserRegisterResponse>(`${API_BASE}/auth/register/elder`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  publicRegisterFamily: (payload: FamilyRegisterRequest) =>
    requestJson<UserRegisterResponse>(`${API_BASE}/auth/register/family`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  publicRegisterCommunityStaff: (payload: CommunityRegisterRequest) =>
    requestJson<UserRegisterResponse>(`${API_BASE}/auth/register/community-staff`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  registerCommunityStaff: (payload: CommunityRegisterRequest, token?: string) =>
    requestJson<UserRegisterResponse>(`${API_BASE}/users/community-staff/register`, {
      method: "POST",
      headers: jsonHeaders(token),
      body: JSON.stringify(payload),
    }),
  me: (token: string) =>
    requestJson<SessionUser>(`${API_BASE}/auth/me`, {
      headers: withBearer(token),
    }),
  getSystemInfo: () => requestJson<SystemInfoResponse>(`${API_BASE}/system/info`),
  getDemoDataStatus: () => requestJson<DemoDataStatus>(`${API_BASE}/system/demo-data/status`),
  refreshDemoData: () =>
    requestJson<{ status: string; message: string; data: DemoDataStatus }>(`${API_BASE}/system/demo-data/refresh`, {
      method: "POST",
    }),
  getChatCapabilities: () => requestJson<ChatCapabilities>(`${API_BASE}/chat/capabilities`),
  getCareAccessProfile: (token: string) =>
    requestJson<CareAccessProfile>(`${API_BASE}/care/access-profile/me`, {
      headers: withBearer(token),
    }),
  getCommunityDashboard: (token: string) =>
    requestJson<CommunityDashboardSummary>(`${API_BASE}/care/community/dashboard`, {
      headers: withBearer(token),
    }),
  getDeviceHistory: (mac: string, window: WindowKind = "day", bucket?: HistoryBucket) =>
    requestJson<DeviceHistoryResponse>(
      `${API_BASE}/health/devices/${mac}/history?window=${window}${bucket ? `&bucket=${bucket}` : ""}`,
    ),
  getCommunityWindowReport: (payload: { window: WindowKind; device_macs?: string[] }) =>
    requestJson<CommunityWindowReportResponse>(`${API_BASE}/health/community/window-report`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  exportCommunityWindowReport: (window: WindowKind = "day", deviceMacs?: string[]) =>
    requestJson<CommunityWindowReportResponse>(
      `${API_BASE}/health/community/window-report/export?window=${window}${
        deviceMacs?.length ? `&${deviceMacs.map((item) => `device_macs=${encodeURIComponent(item)}`).join("&")}` : ""
      }`,
    ),
  getCommunityAgentSummary: (payload: {
    window: WindowKind;
    question: string;
    device_macs?: string[];
    include_web_search?: boolean;
    include_charts?: boolean;
  }) =>
    requestJson<CommunityAgentSummaryResponse>(`${API_BASE}/agent/community/summary`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  getHealthScoreInsight: (payload: HealthScoreInsightRequest) =>
    requestJson<HealthScoreInsightResponse>(`${API_BASE}/agent/health-score/insight`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        window_minutes: 5,
        use_llm: true,
        ...payload,
      }),
    }),
  getAgentElders: (token: string) =>
    requestJson<AgentElderSubject[]>(`${API_BASE}/agent/elders`, {
      headers: withBearer(token),
    }),
  getRobotStatus: (signal?: AbortSignal) =>
    requestJson<RobotStatusResponse>(`${API_BASE}/robot/status`, { signal }),
  listRobotTasks: (
    params: { status?: string; elder_id?: string; outcome?: string; limit?: number } = {},
    signal?: AbortSignal,
  ) => {
    const query = new URLSearchParams();
    if (params.status) query.set("status", params.status);
    if (params.elder_id) query.set("elder_id", params.elder_id);
    if (params.outcome) query.set("outcome", params.outcome);
    query.set("limit", String(params.limit ?? 100));
    return requestJson<RobotTaskListResponse>(`${API_BASE}/robot/tasks?${query.toString()}`, { signal });
  },
  getRobotTask: (taskId: string, signal?: AbortSignal) =>
    requestJson<RobotTaskDetailResponse>(`${API_BASE}/robot/tasks/${taskId}`, { signal }),
  getRobotTaskTimeline: (taskId: string, signal?: AbortSignal) =>
    requestJson<RobotTaskTimelineResponse>(`${API_BASE}/robot/tasks/${taskId}/timeline`, { signal }),
  getRobotTaskObservation: (taskId: string, signal?: AbortSignal) =>
    requestJson<RobotTaskObservationResponse>(`${API_BASE}/robot/tasks/${taskId}/observation`, { signal }),
  cancelRobotTask: (taskId: string) =>
    requestJson<{ ok: boolean; task: RobotTask }>(`${API_BASE}/robot/tasks/${taskId}/cancel`, { method: "POST" }),
  simulateRobotResponse: (taskId: string, payload: { response_type: RobotTaskOutcome; transcript?: string; snapshot_url?: string }) =>
    requestJson<unknown>(`${API_BASE}/robot/tasks/${taskId}/simulate-response`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  getRobotArrivalEvidenceUrl: (taskId: string) => `${API_BASE}/robot/tasks/${taskId}/evidence/arrival.jpg`,
  healthSocket: (mac: string) => new WebSocket(`${WS_BASE}/ws/health/${mac}`),
  alarmSocket: () => new WebSocket(`${WS_BASE}/ws/alarms`),

  // Voice API
  voiceStatus: () =>
    requestJson<{
      configured: boolean;
      asr_model: string | null;
      tts_model: string | null;
      tts_voices: string[];
      provider?: string;
      service_provider?: string;
      note: string;
    }>(`${API_BASE}/voice/status`).then((payload) => ({
      ...payload,
      provider: payload.provider ?? payload.service_provider ?? "none",
    })),
  voiceAsr: async (audioBlob: Blob): Promise<{ ok: boolean; text: string; provider: string; error?: string }> => {
    const form = new FormData();
    form.append("file", audioBlob, "recording.wav");
    const res = await fetch(`${API_BASE}/voice/asr`, { method: "POST", body: form });
    if (!res.ok) throw new Error(`ASR HTTP ${res.status}`);
    return res.json();
  },
  voiceTts: (text: string, voice = "longyingtian", fmt: "mp3" | "wav" = "mp3") =>
    requestJson<{ ok: boolean; audio_b64: string; fmt: string; provider: string; error?: string }>(`${API_BASE}/voice/tts`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, voice, fmt }),
    }),
};
