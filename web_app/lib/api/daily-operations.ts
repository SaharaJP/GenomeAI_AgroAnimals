export type DailyBriefPreviewModel = {
  headline?: string;
  statusLine?: string;
  summary?: string;
  bullets?: string[];
  actions?: Array<{ href: string; count: number; label: string; caption: string }>;
  [key: string]: unknown;
};

export type DailyOperationsBundle = {
  alerts: Record<string, unknown>;
  worklists: Record<string, unknown>;
  planner: Record<string, unknown>;
  reports: Record<string, unknown>;
  decisionIntelligence: Record<string, unknown>;
  partialErrors: string[];
  fetchedAt: string;
};

export type ScopeItem = {
  id: string;
  label: string;
};

export type ScopeVm = {
  tenantId: string;
  farms: ScopeItem[];
  sites: ScopeItem[];
};

export type BriefVm = {
  title: string;
  summary: string;
  whyNow: string;
};

export type AlertVm = {
  id: string;
  title: string;
  status: string;
  severity: string;
  objectType: string;
  objectId: string;
  farmId: string;
  farmLabel: string;
};

export type WorklistVm = {
  id: string;
  title: string;
  status: string;
  priority: string;
  worklistType: string;
  objectType: string;
  objectId: string;
  farmId: string;
  farmLabel: string;
  dueAt: string | null;
};

export type FarmSummaryVm = {
  farmId: string;
  label: string;
  alerts: number;
  tasks: number;
  overdue: number;
};

export type DailyOperationsViewModel = {
  loadedAt: string;
  partialErrors: string[];
  isEmpty: boolean;
  scope: ScopeVm;
  brief: BriefVm;
  totals: {
    alertsOpen: number;
    alertsCritical: number;
    worklistsOpen: number;
    worklistsOverdue: number;
    pendingApprovals: number;
    linkedDecisions: number;
    feedbackAcceptanceRate: number;
  };
  farms: FarmSummaryVm[];
  highlightAlerts: AlertVm[];
  highlightWorklists: WorklistVm[];
};

const API_BASE = '/api/backend';

function isObject(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

function asObject(value: unknown): Record<string, unknown> {
  return isObject(value) ? value : {};
}

function asArray(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function firstString(...values: unknown[]): string {
  for (const value of values) {
    if (typeof value === 'string' && value.trim()) {
      return value.trim();
    }
  }
  return '';
}

function firstNumber(...values: unknown[]): number {
  for (const value of values) {
    if (typeof value === 'number' && Number.isFinite(value)) {
      return value;
    }
    if (typeof value === 'string' && value.trim()) {
      const parsed = Number(value);
      if (Number.isFinite(parsed)) {
        return parsed;
      }
    }
  }
  return 0;
}

function boolFromStatus(status: string, openStatuses: string[]): boolean {
  const value = String(status || '').trim().toLowerCase();
  return openStatuses.includes(value);
}

function fetchArray(payload: Record<string, unknown>, keys: string[]): Record<string, unknown>[] {
  for (const key of keys) {
    const raw = payload[key];
    if (Array.isArray(raw)) {
      return raw.filter(isObject);
    }
  }
  return [];
}

function withCacheBust(path: string): string {
  const glue = path.includes('?') ? '&' : '?';
  return `${path}${glue}_ts=${Date.now()}`;
}

async function fetchJson(path: string): Promise<Record<string, unknown>> {
  const response = await fetch(withCacheBust(path), {
    method: 'GET',
    credentials: 'include',
    cache: 'no-store',
    headers: {
      accept: 'application/json',
    },
  });

  const text = await response.text();
  let payload: Record<string, unknown> = {};

  if (text.trim()) {
    try {
      const parsed = JSON.parse(text);
      payload = asObject(parsed);
    } catch {
      payload = {};
    }
  }

  if (!response.ok) {
    const detail = firstString(payload.detail, payload.message, payload.error);
    throw new Error(detail || `HTTP ${response.status} for ${path}`);
  }

  return payload;
}

async function safeFetch(path: string): Promise<{ ok: true; data: Record<string, unknown> } | { ok: false; error: string }> {
  try {
    const data = await fetchJson(path);
    return { ok: true, data };
  } catch (error) {
    return {
      ok: false,
      error: error instanceof Error ? error.message : `Failed request: ${path}`,
    };
  }
}

function normalizeAlert(row: Record<string, unknown>, index: number): AlertVm {
  const id = firstString(row.alert_id, row.id) || `alert-${index + 1}`;
  const title =
    firstString(row.title, row.message, row.alert_type, row.object_id) ||
    `Alert ${index + 1}`;
  const farmId = firstString(row.farm_id) || 'unscoped';
  return {
    id,
    title,
    status: firstString(row.status) || 'unknown',
    severity: firstString(row.severity, row.priority) || 'normal',
    objectType: firstString(row.object_type) || 'object',
    objectId: firstString(row.object_id) || '—',
    farmId,
    farmLabel: farmId,
  };
}

function normalizeWorklist(row: Record<string, unknown>, index: number): WorklistVm {
  const id = firstString(row.task_id, row.worklist_id, row.id) || `worklist-${index + 1}`;
  const title =
    firstString(row.title, row.summary, row.task_type, row.worklist_type, row.object_id) ||
    `Worklist ${index + 1}`;
  const farmId = firstString(row.farm_id) || 'unscoped';
  return {
    id,
    title,
    status: firstString(row.status) || 'unknown',
    priority: firstString(row.priority) || 'normal',
    worklistType: firstString(row.worklist_type, row.task_type) || 'general',
    objectType: firstString(row.object_type) || 'object',
    objectId: firstString(row.object_id) || '—',
    farmId,
    farmLabel: farmId,
    dueAt: firstString(row.due_at, row.deadline) || null,
  };
}

function buildScope(bundle: DailyOperationsBundle): ScopeVm {
  const alerts = fetchArray(bundle.alerts, ['items', 'alerts']);
  const worklists = fetchArray(bundle.worklists, ['items', 'worklists', 'tasks']);
  const di = asObject(bundle.decisionIntelligence);
  const summary = asObject(di.summary);

  const farmMap = new Map<string, ScopeItem>();
  const siteMap = new Map<string, ScopeItem>();

  for (const row of [...alerts, ...worklists]) {
    const farmId = firstString(row.farm_id);
    const siteId = firstString(row.site_id);
    if (farmId) farmMap.set(farmId, { id: farmId, label: farmId });
    if (siteId) siteMap.set(siteId, { id: siteId, label: siteId });
  }

  return {
    tenantId: firstString(summary.tenant_id) || 'default',
    farms: Array.from(farmMap.values()),
    sites: Array.from(siteMap.values()),
  };
}

function buildBrief(isEmpty: boolean, totals: DailyOperationsViewModel['totals']): BriefVm {
  if (isEmpty) {
    return {
      title: 'Runtime contour is healthy, but daily operational data is empty',
      summary:
        'Страница открылась корректно, но в runtime пока нет alerts, worklists и decision/feedback записей для start-of-day summary.',
      whyNow:
        'После загрузки demo или боевых данных карточки, таблицы и linked actions автоматически заполнятся без дополнительной миграции UI.',
    };
  }

  return {
    title: 'Operational daily summary is available',
    summary: `Открытых alerts: ${totals.alertsOpen}. Открытых worklists: ${totals.worklistsOpen}. Linked decisions: ${totals.linkedDecisions}.`,
    whyNow:
      'React summary уже использует canonical backend DTOs и показывает стартовую operational картину по текущему runtime состоянию.',
  };
}

export async function fetchDailyOperationsBundle(): Promise<DailyOperationsBundle> {
  const [alerts, worklists, planner, reports, decisionIntelligence] = await Promise.all([
    safeFetch(`${API_BASE}/alerts?limit=50`),
    safeFetch(`${API_BASE}/worklists?limit=50`),
    safeFetch(`${API_BASE}/planner?limit=50`),
    safeFetch(`${API_BASE}/reports?limit=20`),
    safeFetch(`${API_BASE}/decision-intelligence?limit=20`),
  ]);

  const partialErrors = [alerts, worklists, planner, reports, decisionIntelligence]
    .filter((item): item is { ok: false; error: string } => !item.ok)
    .map((item) => item.error);

  const okCount = [alerts, worklists, planner, reports, decisionIntelligence].filter((item) => item.ok).length;
  if (okCount === 0) {
    throw new Error(partialErrors.join(' | ') || 'All daily summary requests failed');
  }

  return {
    alerts: alerts.ok ? alerts.data : {},
    worklists: worklists.ok ? worklists.data : {},
    planner: planner.ok ? planner.data : {},
    reports: reports.ok ? reports.data : {},
    decisionIntelligence: decisionIntelligence.ok ? decisionIntelligence.data : {},
    partialErrors,
    fetchedAt: new Date().toISOString(),
  };
}

export function buildDailyOperationsViewModel(bundle: DailyOperationsBundle): DailyOperationsViewModel {
  const alertsPayload = asObject(bundle.alerts);
  const worklistsPayload = asObject(bundle.worklists);
  const plannerPayload = asObject(bundle.planner);
  const reportsPayload = asObject(bundle.reports);
  const diPayload = asObject(bundle.decisionIntelligence);
  const diSummary = asObject(diPayload.summary);

  const alerts = fetchArray(alertsPayload, ['items', 'alerts']).map(normalizeAlert);
  const worklists = fetchArray(worklistsPayload, ['items', 'worklists', 'tasks']).map(normalizeWorklist);

  const alertsOpen = alerts.filter((item) => boolFromStatus(item.status, ['new', 'acknowledged', 'open'])).length;
  const alertsCritical = alerts.filter((item) => ['critical', 'high'].includes(String(item.severity).toLowerCase())).length;
  const worklistsOpen = worklists.filter((item) => boolFromStatus(item.status, ['open', 'in_progress', 'queued'])).length;
  const worklistsOverdue = worklists.filter((item) => boolFromStatus(item.status, ['overdue'])).length;

  const acceptedFeedback = firstNumber(diSummary.accepted_feedback, diSummary.acceptedFeedback);
  const rejectedFeedback = firstNumber(diSummary.rejected_feedback, diSummary.rejectedFeedback);
  const linkedDecisions = firstNumber(diSummary.total_decisions, diSummary.totalDecisions);
  const pendingApprovals =
    firstNumber(
      asObject(plannerPayload.summary).pending_approvals,
      asObject(reportsPayload.summary).pending_approvals,
      asObject(reportsPayload.summary).pendingApprovals,
    );

  const acceptanceBase = acceptedFeedback + rejectedFeedback;
  const feedbackAcceptanceRate = acceptanceBase > 0 ? acceptedFeedback / acceptanceBase : 0;

  const farmMap = new Map<string, FarmSummaryVm>();
  for (const item of alerts) {
    const current = farmMap.get(item.farmId) || {
      farmId: item.farmId,
      label: item.farmLabel,
      alerts: 0,
      tasks: 0,
      overdue: 0,
    };
    current.alerts += 1;
    farmMap.set(item.farmId, current);
  }
  for (const item of worklists) {
    const current = farmMap.get(item.farmId) || {
      farmId: item.farmId,
      label: item.farmLabel,
      alerts: 0,
      tasks: 0,
      overdue: 0,
    };
    current.tasks += 1;
    if (String(item.status).toLowerCase() === 'overdue') {
      current.overdue += 1;
    }
    farmMap.set(item.farmId, current);
  }

  const totals = {
    alertsOpen,
    alertsCritical,
    worklistsOpen,
    worklistsOverdue,
    pendingApprovals,
    linkedDecisions,
    feedbackAcceptanceRate,
  };

  const isEmpty =
    alerts.length === 0 &&
    worklists.length === 0 &&
    linkedDecisions === 0 &&
    acceptedFeedback === 0 &&
    rejectedFeedback === 0;

  return {
    loadedAt: bundle.fetchedAt,
    partialErrors: bundle.partialErrors,
    isEmpty,
    scope: buildScope(bundle),
    brief: buildBrief(isEmpty, totals),
    totals,
    farms: Array.from(farmMap.values()).sort((a, b) => a.label.localeCompare(b.label)),
    highlightAlerts: alerts.slice(0, 5),
    highlightWorklists: worklists.slice(0, 5),
  };
}
