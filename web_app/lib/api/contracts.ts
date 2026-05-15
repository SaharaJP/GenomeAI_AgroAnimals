export type ApiLinkage = {
  data_version?: string | null;
  qc_run?: string | null;
  model_version?: string | null;
  scoring_run?: string | null;
  report_version?: string | null;
  request_id?: string | null;
};

export type AuthUserView = {
  user_id: number;
  username: string;
  role: string;
  permissions: string[];
  collaboration_mode?: string | null;
  external_org?: string | null;
};

export type AuthScope = {
  tenant_id: string;
  allowed_farm_ids: string[];
  allowed_site_ids: string[];
  active_farm_id?: string | null;
  active_site_id?: string | null;
};

export type AuthSessionView = {
  session_id: string;
  client_kind: string;
  auth_transport: string;
  status: string;
  created_at: string;
  updated_at: string;
  last_seen_at?: string | null;
  expires_at?: string | null;
  refresh_expires_at?: string | null;
};

export type AuthMeResponse = {
  schema: string;
  user: AuthUserView;
  session: AuthSessionView;
  scope: AuthScope;
  demo_mode?: boolean;
};

export type EntityRef = {
  object_type: string;
  object_id: string;
  farm_id?: string | null;
  group_id?: string | null;
  label?: string | null;
};

export type AlertItem = {
  alert_id: string;
  status: string;
  alert_type: string;
  title: string;
  source?: string | null;
  cause?: string | null;
  severity?: string | null;
  confidence?: number | null;
  owner_user_id?: number | null;
  owner_username?: string | null;
  deadline?: string | null;
  entity: EntityRef;
  linkage: ApiLinkage;
  why?: Record<string, unknown>;
  what_to_do?: Array<Record<string, unknown>>;
  attachments?: Array<Record<string, unknown>>;
  created_at?: string | null;
  updated_at?: string | null;
};

export type WorklistItem = {
  task_id: string;
  status: string;
  task_type: string;
  title: string;
  domain?: string | null;
  priority: number;
  due_at?: string | null;
  stage?: string | null;
  assignee_team?: string | null;
  owner_user_id?: number | null;
  owner_username?: string | null;
  related_alert?: string | null;
  worklist_type?: string | null;
  confidence?: number | null;
  entity?: EntityRef | null;
  linkage: ApiLinkage;
  why?: Record<string, unknown>;
  what_to_do?: Array<Record<string, unknown>>;
  attachments?: Array<Record<string, unknown>>;
  created_at?: string | null;
  updated_at?: string | null;
  is_overdue?: boolean | null;
  source_insight_id?: string | null;
};

export type PlannerPlanItem = {
  plan_id: string;
  status: string;
  name: string;
  week_start: string;
  item_count: number;
  citation_count: number;
  farm_id?: string | null;
  linkage: ApiLinkage;
  approval_requested_at?: string | null;
  approval_requested_by_username?: string | null;
  approved_at?: string | null;
  approved_by_username?: string | null;
};

export type PlannerSummary = {
  alerts_new: number;
  alerts_acknowledged: number;
  alerts_resolved: number;
  tasks_open: number;
  tasks_done: number;
  overdue_active: number;
};

export type PlannerResponse = {
  schema: string;
  summary: PlannerSummary;
  pending_approvals: number;
  weekly_plans: PlannerPlanItem[];
  overdue_items: WorklistItem[];
};

export type DecisionItem = {
  decision_id: string;
  created_at: string;
  action: string;
  username: string;
  user_id?: number | null;
  reason?: string | null;
  comment?: string | null;
  related_alert?: string | null;
  recommendation_id?: string | null;
  entity?: EntityRef | null;
  linkage: ApiLinkage;
  metadata?: Record<string, unknown>;
};

export type FeedbackMetrics = {
  total_feedback: number;
  accepted_count: number;
  rejected_count: number;
  acceptance_rate: number;
  median_decision_seconds?: number | null;
};

export type FeedbackItem = {
  feedback_id: string;
  created_at: string;
  decision: string;
  reason_code: string;
  comment?: string | null;
  recommendation_id?: string | null;
  related_alert?: string | null;
  task_id?: string | null;
  entity?: EntityRef | null;
  linkage: ApiLinkage;
  feedback_source?: string | null;
  metadata?: Record<string, unknown>;
};

export type ReportItem = {
  data_version: string;
  report_version: string;
  status: string;
  approved_at?: string | null;
  approved_by_username?: string | null;
  comment?: string | null;
  linkage: ApiLinkage;
};

export type ReportsListResponse = {
  schema: string;
  total: number;
  items: ReportItem[];
};

export type AnimalAttributes = {
  name?: string | null;
  breed?: string | null;
  birth_date?: string | null;
  lactation_number?: number | null;
  days_in_milk?: number | null;
  last_calving_date?: string | null;
  total_calvings?: number | null;
  reproduction_status?: string | null;
  next_calving_expected?: string | null;
  group_label?: string | null;
  farm_label?: string | null;
};

export type HealthMetrics = {
  activity_score?: number | null;
  activity_norm?: number | null;
  scc?: number | null;
  scc_trend?: string | null;
  body_condition_score?: number | null;
  daily_milk_yield_kg?: number | null;
};

export type HealthEvent = {
  event_id?: string | null;
  event_date?: string | null;
  event_type?: string | null;
  severity?: string | null;
  notes?: string | null;
  treatment?: string | null;
};

export type ProfileResponse = {
  schema: string;
  entity: EntityRef;
  summary: {
    alerts_open: number;
    worklists_open: number;
    decisions_total: number;
  };
  alerts: AlertItem[];
  worklists: WorklistItem[];
  decisions: DecisionItem[];
  animal_attributes?: AnimalAttributes | null;
  health_metrics?: HealthMetrics | null;
  recent_health_events?: HealthEvent[];
};

export type DecisionIntelligenceResponse = {
  schema: string;
  summary: {
    total_decisions: number;
    accepted_feedback: number;
    rejected_feedback: number;
    acceptance_rate: number;
    linked_alerts: number;
  };
  top_actions: Array<{ action: string; count: number }>;
  latest_decisions: DecisionItem[];
};

export type EconomicsScenarioItem = {
  scenario_id: string;
  name: string;
  status: string;
  description?: string | null;
  data_version?: string | null;
  last_economics_run?: string | null;
  report_version?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
};

export type EconomicsListResponse = {
  schema: string;
  scenarios_total: number;
  reports_total: number;
  scenario_items: EconomicsScenarioItem[];
  report_items: Array<Record<string, unknown>>;
};

export type SupportResponse = {
  schema: string;
  release?: Record<string, unknown>;
  observability?: Record<string, unknown>;
  summary?: {
    open_support_cases: number;
    open_incidents: number;
    critical_open_incidents: number;
    diagnostics_available: number;
    support_bundle_count: number;
    release_notes_total: number;
  };
  source_paths?: Record<string, string>;
};

export type PilotPackItem = {
  pack_id: string;
  data_version: string;
  created_at?: string | null;
  status: string;
  file_count: number;
  linkage: ApiLinkage;
  source_paths: Record<string, string>;
};

export type PilotResponse = {
  schema: string;
  summary: {
    total_pilot_packs: number;
    latest_data_version?: string | null;
    latest_pack_id?: string | null;
  };
  items: PilotPackItem[];
};

export type ReadinessCheck = {
  check_id: string;
  status: string;
  severity: string;
  message: string;
};

export type ReadinessResponse = {
  schema: string;
  profile?: string | null;
  summary: {
    overall_status: string;
    checks_total: number;
    passed: number;
    warnings: number;
    failed: number;
  };
  checks: ReadinessCheck[];
  source_paths: Record<string, unknown>;
};

export type RecommendedTask = {
  recommended_task_id: string;
  source_insight_id: string;
  title: string;
  description?: string | null;
  priority: number;
  due_at?: string | null;
  assignee_role?: string | null;
  assignee_user_id?: number | null;
  domain?: string | null;
  why_summary: string;
};

export type RecommendedTasksListResponse = {
  schema: string;
  total: number;
  items: RecommendedTask[];
};

export type WorklistsFromRecommendedItem = {
  recommended_task_id: string;
  source_insight_id: string;
  task_id: string;
  created: boolean;
};

export type WorklistsFromRecommendedResponse = {
  schema: string;
  total: number;
  created: number;
  reused: number;
  items: WorklistsFromRecommendedItem[];
};

export type FeedingRation = {
  group_id: string;
  group_name: string;
  ration_name: string;
  dm_kg?: number | null;
  last_distribution_at?: string | null;
  status: string;
};

export type FeedingRationsResponse = {
  schema: string;
  total: number;
  items: FeedingRation[];
};

export type FeedIntakeDrop = {
  insight_id: string;
  group_id?: string | null;
  group_name?: string | null;
  drop_pct?: number | null;
  window_days?: number | null;
  last_observed_at?: string | null;
  title: string;
};

export type FeedIntakeDropsResponse = {
  schema: string;
  total: number;
  items: FeedIntakeDrop[];
};

export type BriefingScheduleResponse = {
  schema: string;
  tenant_id: string;
  periodicity: 'daily' | 'weekly' | 'monthly';
  time_of_day: string;
  auto_create_tasks: boolean;
  updated_at?: string | null;
  updated_by?: number | null;
};

export type BriefingScheduleRequest = {
  periodicity: 'daily' | 'weekly' | 'monthly';
  time_of_day: string;
  auto_create_tasks: boolean;
};

export type ListResponse<T> = {
  schema: string;
  total: number;
  limit?: number;
  offset?: number;
  items: T[];
};

export type Personnel = {
  personnel_id: string;
  full_name: string;
  position: string;
  group_id?: string | null;
  photo_ref?: string | null;
  phone?: string | null;
  email?: string | null;
  hired_at?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
};

export type PersonnelCreateRequest = {
  full_name: string;
  position: string;
  group_id?: string | null;
  phone?: string | null;
  email?: string | null;
  hired_at?: string | null;
};

export type PersonnelUpdateRequest = {
  full_name?: string | null;
  position?: string | null;
  group_id?: string | null;
  phone?: string | null;
  email?: string | null;
  hired_at?: string | null;
  photo_ref?: string | null;
};

export type PersonnelListResponse = {
  schema: string;
  total: number;
  pii_visible: boolean;
  items: Personnel[];
};

export type PersonnelResponse = {
  schema: string;
  pii_visible: boolean;
  item: Personnel;
};

export function normalizeListResponse<T>(input: Partial<ListResponse<T>>): ListResponse<T> {
  return {
    schema: input.schema || 'genomeai.api.unknown.list.v1',
    total: input.total ?? (input.items?.length || 0),
    limit: input.limit,
    offset: input.offset,
    items: input.items || [],
  };
}

export function hasPermission(me: AuthMeResponse | null, permission: string): boolean {
  return Boolean(me?.user.permissions.includes(permission));
}

export type DomainLabelsResponse = {
  schema: string;
  locale: string;
  labels: Record<string, string>;
};
