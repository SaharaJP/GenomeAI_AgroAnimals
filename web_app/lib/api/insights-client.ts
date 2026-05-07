import type { InsightItem, InsightRecommendation } from './insights';

export interface InsightSettings {
  min_severity: 'info' | 'warn' | 'high' | 'urgent';
  enabled_categories: string[];
}

export interface ScanNowResult {
  count: number;
  insight_ids: string[];
  skipped?: boolean;
  skip_reason?: string | null;
}

export async function fetchInsights(params?: {
  farmId?: string;
  status?: string;
  category?: string;
  severityMin?: string;
}): Promise<{ total: number; items: InsightItem[] }> {
  const qs = new URLSearchParams();
  if (params?.farmId) qs.set('farm_id', params.farmId);
  if (params?.status) qs.set('status', params.status);
  if (params?.category) qs.set('category', params.category);
  if (params?.severityMin) qs.set('severity_min', params.severityMin);
  const r = await fetch(`/api/insights?${qs.toString()}`, { cache: 'no-store' });
  if (!r.ok) throw new Error(`fetchInsights ${r.status}`);
  return r.json();
}

export async function fetchInsight(id: string): Promise<InsightItem> {
  const r = await fetch(`/api/insights/${encodeURIComponent(id)}`, { cache: 'no-store' });
  if (!r.ok) throw new Error(`fetchInsight ${r.status}`);
  return r.json();
}

export interface InsightPatchBody {
  title?: string;
  body?: string;
  action?: string;
  recommendations?: InsightRecommendation[];
}

export async function patchInsight(id: string, body: InsightPatchBody): Promise<InsightItem> {
  const r = await fetch(`/api/insights/${encodeURIComponent(id)}`, {
    method: 'PATCH',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`patchInsight ${r.status}`);
  return r.json();
}

export async function deleteInsight(id: string): Promise<void> {
  const r = await fetch(`/api/insights/${encodeURIComponent(id)}`, { method: 'DELETE' });
  if (!r.ok) throw new Error(`deleteInsight ${r.status}`);
}

export async function transitionInsight(id: string, status: string): Promise<InsightItem> {
  const r = await fetch(`/api/insights/${encodeURIComponent(id)}/transition`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ status }),
  });
  if (!r.ok) throw new Error(`transitionInsight ${r.status}`);
  return r.json();
}

export async function scanNow(farmId: string): Promise<ScanNowResult> {
  const r = await fetch(`/api/insights/scan-now?farm_id=${encodeURIComponent(farmId)}`, {
    method: 'POST',
  });
  if (r.status === 409) throw new Error('scan_in_progress');
  if (r.status === 503) throw new Error('ai_unavailable');
  if (!r.ok) throw new Error(`scanNow ${r.status}`);
  return r.json();
}

export async function fetchSettings(farmId: string): Promise<InsightSettings> {
  const r = await fetch(`/api/insights/settings?farm_id=${encodeURIComponent(farmId)}`, {
    cache: 'no-store',
  });
  if (!r.ok) throw new Error(`fetchSettings ${r.status}`);
  return r.json();
}

export async function putSettings(farmId: string, body: InsightSettings): Promise<InsightSettings> {
  const r = await fetch(`/api/insights/settings?farm_id=${encodeURIComponent(farmId)}`, {
    method: 'PUT',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`putSettings ${r.status}`);
  return r.json();
}
