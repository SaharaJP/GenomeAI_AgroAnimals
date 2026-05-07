export type QcSeverity = 'info' | 'warn' | 'high';
export type QcStatus = 'active' | 'resolved' | 'dismissed';

export interface QcIncident {
  incident_id: string;
  farm_id: string;
  metric_id: string;
  period_start: string;
  period_end: string | null;
  detector_type: string;
  severity: QcSeverity;
  affected_sensors: string[];
  ai_description: string | null;
  root_cause: string | null;
  status: QcStatus;
  detected_at: string;
}

export async function fetchQcIncidents(params: {
  farmId: string;
  metricId?: string;
  active?: boolean;
}): Promise<{ total: number; items: QcIncident[] }> {
  const qs = new URLSearchParams();
  qs.set('farm_id', params.farmId);
  if (params.metricId) qs.set('metric_id', params.metricId);
  if (params.active !== undefined) qs.set('active', String(params.active));
  const r = await fetch(`/api/qc/incidents?${qs.toString()}`, { cache: 'no-store' });
  if (!r.ok) throw new Error(`fetchQcIncidents ${r.status}`);
  return r.json();
}

export async function fetchQcIncident(id: string): Promise<QcIncident> {
  const r = await fetch(`/api/qc/incidents/${encodeURIComponent(id)}`, { cache: 'no-store' });
  if (!r.ok) throw new Error(`fetchQcIncident ${r.status}`);
  return r.json();
}

export async function dismissQcIncident(id: string): Promise<{ incident_id: string; status: string }> {
  const r = await fetch(`/api/qc/incidents/${encodeURIComponent(id)}/dismiss`, { method: 'POST' });
  if (!r.ok) throw new Error(`dismissQcIncident ${r.status}`);
  return r.json();
}
