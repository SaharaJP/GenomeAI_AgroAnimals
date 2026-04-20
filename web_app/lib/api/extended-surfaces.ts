import { apiFetch, authFetch } from '@/lib/api/client';
import type {
  AlertItem,
  AuthMeResponse,
  DecisionIntelligenceResponse,
  EconomicsListResponse,
  ListResponse,
  PilotResponse,
  PlannerResponse,
  ReadinessResponse,
  SupportResponse,
  WorklistItem,
} from '@/lib/api/contracts';
import { normalizeListResponse } from '@/lib/api/contracts';

export type ExtendedBundle = {
  me: AuthMeResponse;
  alerts: ListResponse<AlertItem>;
  worklists: ListResponse<WorklistItem>;
  planner: PlannerResponse;
  decisionIntelligence: DecisionIntelligenceResponse;
  economics: EconomicsListResponse;
  support: SupportResponse;
  pilot: PilotResponse;
  readiness: ReadinessResponse;
  adminMatrix: Record<string, unknown>;
  observability: Record<string, unknown>;
};

export type EnterpriseScopeModel = {
  tenantId: string;
  mode: 'single-farm' | 'multi-site';
  activeFarmId?: string | null;
  activeSiteId?: string | null;
  farmCountVisible: number;
  siteCountVisible: number;
};

export type ReproductionViewModel = {
  summary: {
    openWorklists: number;
    overdueWorklists: number;
    activeAlerts: number;
    pendingApprovals: number;
  };
  scope: EnterpriseScopeModel;
  worklists: WorklistItem[];
  alerts: AlertItem[];
  planPreview: PlannerResponse['weekly_plans'];
  parityNote: string;
};

export type VetViewModel = {
  summary: {
    queueItems: number;
    overdueItems: number;
    highSeverityAlerts: number;
    linkedDecisions: number;
  };
  scope: EnterpriseScopeModel;
  worklists: WorklistItem[];
  alerts: AlertItem[];
  parityNote: string;
};

export type TreatmentViewModel = {
  summary: {
    treatmentTasks: number;
    withdrawalWatch: number;
    healthAlerts: number;
    diagnosticsAvailable: number;
  };
  scope: EnterpriseScopeModel;
  worklists: WorklistItem[];
  alerts: AlertItem[];
  rulesEvidence: string[];
  parityNote: string;
};

export type EconomicsViewModel = {
  summary: {
    scenariosTotal: number;
    reportsTotal: number;
    decisionAcceptanceRate: number;
    supportBundles: number;
  };
  scope: EnterpriseScopeModel;
  scenarios: EconomicsListResponse['scenario_items'];
  reportItems: EconomicsListResponse['report_items'];
};

export type AdminViewModel = {
  summary: {
    roleCount: number;
    permissionRows: number;
    diagnosticsAvailable: number;
    readinessChecks: number;
    pilotPacks: number;
  };
  scope: EnterpriseScopeModel;
  permissionMatrix: Record<string, unknown>;
  observability: Record<string, unknown>;
  support: SupportResponse;
  readiness: ReadinessResponse;
  pilot: PilotResponse;
};

export async function fetchExtendedBundle(): Promise<ExtendedBundle> {
  const emptyDecisionIntelligence: DecisionIntelligenceResponse = {
    schema: 'genomeai.api.decision_intelligence.summary.v1',
    summary: {
      total_decisions: 0,
      accepted_feedback: 0,
      rejected_feedback: 0,
      acceptance_rate: 0,
      linked_alerts: 0,
    },
    top_actions: [],
    latest_decisions: [],
  };

  const [me, alerts, worklists, planner, decisionIntelligence, economics, support, pilot, readiness, adminMatrix, observability] = await Promise.all([
    authFetch<AuthMeResponse>('/me'),
    apiFetch<ListResponse<AlertItem>>('/alerts'),
    apiFetch<ListResponse<WorklistItem>>('/worklists'),
    apiFetch<PlannerResponse>('/planner'),
    apiFetch<DecisionIntelligenceResponse>('/decision-intelligence').catch(() => emptyDecisionIntelligence),
    apiFetch<EconomicsListResponse>('/economics'),
    apiFetch<SupportResponse>('/support'),
    apiFetch<PilotResponse>('/pilot'),
    apiFetch<ReadinessResponse>('/readiness'),
    fetch('/api/admin/permission-matrix', { credentials: 'include', cache: 'no-store' }).then((r) => r.json() as Promise<Record<string, unknown>>),
    fetch('/api/observability', { credentials: 'include', cache: 'no-store' }).then((r) => r.json() as Promise<Record<string, unknown>>),
  ]);

  return {
    me,
    alerts: normalizeListResponse(alerts),
    worklists: normalizeListResponse(worklists),
    planner,
    decisionIntelligence,
    economics,
    support,
    pilot,
    readiness,
    adminMatrix,
    observability,
  };
}

function buildScope(me: AuthMeResponse): EnterpriseScopeModel {
  const farmCountVisible = Math.max(me.scope.allowed_farm_ids.length, me.scope.active_farm_id ? 1 : 0);
  const siteCountVisible = Math.max(me.scope.allowed_site_ids.length, me.scope.active_site_id ? 1 : 0);
  return {
    tenantId: me.scope.tenant_id,
    mode: farmCountVisible > 1 ? 'multi-site' : 'single-farm',
    activeFarmId: me.scope.active_farm_id,
    activeSiteId: me.scope.active_site_id,
    farmCountVisible,
    siteCountVisible,
  };
}

function lc(value: unknown): string {
  return String(value || '').toLowerCase();
}

function isReproductionWorklist(item: WorklistItem): boolean {
  return item.worklist_type === 'reproduction' || lc(item.domain) === 'repro' || lc(item.task_type).includes('repro');
}

function isReproductionAlert(item: AlertItem): boolean {
  const haystack = [item.alert_type, item.title, item.cause].map(lc).join(' ');
  return haystack.includes('repro') || haystack.includes('preg') || haystack.includes('calv') || haystack.includes('insemin');
}

function isVetWorklist(item: WorklistItem): boolean {
  const wt = lc(item.worklist_type);
  const domain = lc(item.domain);
  return wt === 'vet' || wt === 'vet_triage' || wt === 'health_follow_up' || domain === 'health' || lc(item.assignee_team) === 'vet';
}

function isVetAlert(item: AlertItem): boolean {
  const haystack = [item.alert_type, item.title, item.cause].map(lc).join(' ');
  return haystack.includes('mastit') || haystack.includes('keto') || haystack.includes('lameness') || haystack.includes('metrit') || haystack.includes('health') || haystack.includes('vet');
}

function isTreatmentWorklist(item: WorklistItem): boolean {
  const haystack = [item.task_type, item.title, item.domain, item.worklist_type].map(lc).join(' ');
  return haystack.includes('treat') || haystack.includes('withdraw') || haystack.includes('drug') || haystack.includes('protocol') || haystack.includes('health');
}

function isTreatmentAlert(item: AlertItem): boolean {
  const haystack = [item.alert_type, item.title, item.cause].map(lc).join(' ');
  return haystack.includes('withdraw') || haystack.includes('treat') || haystack.includes('drug') || haystack.includes('mastit') || haystack.includes('milk');
}

export function buildReproductionViewModel(bundle: ExtendedBundle): ReproductionViewModel {
  const worklists = bundle.worklists.items.filter(isReproductionWorklist);
  const alerts = bundle.alerts.items.filter(isReproductionAlert);
  return {
    summary: {
      openWorklists: worklists.filter((item) => item.status !== 'done' && item.status !== 'cancelled').length,
      overdueWorklists: worklists.filter((item) => item.is_overdue && item.status !== 'done' && item.status !== 'cancelled').length,
      activeAlerts: alerts.filter((item) => item.status !== 'resolved').length,
      pendingApprovals: bundle.planner.pending_approvals,
    },
    scope: buildScope(bundle.me),
    worklists: worklists.slice(0, 8),
    alerts: alerts.slice(0, 8),
    planPreview: bundle.planner.weekly_plans.slice(0, 5),
    parityNote: 'React uses backend evidence from worklist_type/domain/linkage and planner approvals. No reproduction logic is reimplemented in the browser.',
  };
}

export function buildVetViewModel(bundle: ExtendedBundle): VetViewModel {
  const worklists = bundle.worklists.items.filter(isVetWorklist);
  const alerts = bundle.alerts.items.filter(isVetAlert);
  return {
    summary: {
      queueItems: worklists.filter((item) => item.status !== 'done' && item.status !== 'cancelled').length,
      overdueItems: worklists.filter((item) => item.is_overdue && item.status !== 'done' && item.status !== 'cancelled').length,
      highSeverityAlerts: alerts.filter((item) => ['high', 'critical'].includes(lc(item.severity)) && item.status !== 'resolved').length,
      linkedDecisions: bundle.decisionIntelligence.summary.linked_alerts,
    },
    scope: buildScope(bundle.me),
    worklists: worklists.slice(0, 8),
    alerts: alerts.slice(0, 8),
    parityNote: 'Vet queues stay anchored to backend-issued worklists, alerts and decision linkage. React only groups the server evidence into a queue surface.',
  };
}

export function buildTreatmentViewModel(bundle: ExtendedBundle): TreatmentViewModel {
  const worklists = bundle.worklists.items.filter(isTreatmentWorklist);
  const alerts = bundle.alerts.items.filter(isTreatmentAlert);
  return {
    summary: {
      treatmentTasks: worklists.filter((item) => item.status !== 'done' && item.status !== 'cancelled').length,
      withdrawalWatch: alerts.filter((item) => item.status !== 'resolved').length,
      healthAlerts: bundle.alerts.items.filter(isVetAlert).length,
      diagnosticsAvailable: Number(bundle.support.summary?.diagnostics_available || 0),
    },
    scope: buildScope(bundle.me),
    worklists: worklists.slice(0, 8),
    alerts: alerts.slice(0, 8),
    rulesEvidence: [
      'Withdrawal / treatment surface uses backend health worklists and alerts only.',
      'Diagnostics, support bundles and report lineage remain server-governed.',
      'React does not invent treatment protocol logic; it only shows backend-linked evidence.',
    ],
    parityNote: 'Treatment and withdrawal parity in React is backed by backend health worklists, alerts and support diagnostics.',
  };
}

export function buildEconomicsViewModel(bundle: ExtendedBundle): EconomicsViewModel {
  return {
    summary: {
      scenariosTotal: bundle.economics.scenarios_total,
      reportsTotal: bundle.economics.reports_total,
      decisionAcceptanceRate: bundle.decisionIntelligence.summary.acceptance_rate,
      supportBundles: Number(bundle.support.summary?.support_bundle_count || 0),
    },
    scope: buildScope(bundle.me),
    scenarios: bundle.economics.scenario_items,
    reportItems: bundle.economics.report_items,
  };
}

export function buildAdminViewModel(bundle: ExtendedBundle): AdminViewModel {
  const matrix = bundle.adminMatrix;
  const roleRows = Array.isArray(matrix?.roles) ? matrix.roles.length : Array.isArray(matrix?.rows) ? matrix.rows.length : 0;
  const permissionRows = Array.isArray(matrix?.permissions) ? matrix.permissions.length : Array.isArray(matrix?.rows) ? matrix.rows.length : 0;
  return {
    summary: {
      roleCount: roleRows,
      permissionRows,
      diagnosticsAvailable: Number(bundle.support.summary?.diagnostics_available || 0),
      readinessChecks: bundle.readiness.summary.checks_total,
      pilotPacks: bundle.pilot.summary.total_pilot_packs,
    },
    scope: buildScope(bundle.me),
    permissionMatrix: matrix,
    observability: bundle.observability,
    support: bundle.support,
    readiness: bundle.readiness,
    pilot: bundle.pilot,
  };
}
