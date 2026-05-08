export type AiStats = {
  period_hours: number;
  count: number;
  p50_latency_ms: number;
  p95_latency_ms: number;
  total_input_tokens: number;
  total_output_tokens: number;
  total_tokens: number;
  total_cost_usd: number;
  error_count: number;
  error_rate: number;
};

export type AiCallRow = {
  id: number;
  created_at: string;
  endpoint: string;
  model: string;
  user_id: string | null;
  latency_ms: number;
  total_tokens: number;
  cost_usd: number;
  has_error: boolean;
};

export type AiCallDetail = AiCallRow & {
  task_type: string;
  input_tokens: number;
  output_tokens: number;
  cache_creation_tokens: number;
  cache_read_tokens: number;
  error: string | null;
  prompt: string | null;
  response: string | null;
  evidence_chips: string[] | null;
  tools_used: Array<Record<string, unknown>> | null;
};

export type GroundingRate = {
  period_hours: number;
  with_evidence: number;
  without_evidence: number;
  total: number;
  rate_pct: number;
};

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(path, { credentials: 'include', cache: 'no-store' });
  if (res.status === 403) throw new Error('forbidden');
  if (!res.ok) throw new Error(`request failed: ${res.status}`);
  return res.json() as Promise<T>;
}

export function fetchAiStats(periodHours: 1 | 24 | 168 = 24): Promise<AiStats> {
  return getJson<AiStats>(`/api/admin/ai/stats?period_hours=${periodHours}`);
}

export function fetchAiCalls(opts: { limit?: number; endpoint?: string; userId?: string; status?: 'ok' | 'error' } = {}): Promise<AiCallRow[]> {
  const sp = new URLSearchParams();
  if (opts.limit) sp.set('limit', String(opts.limit));
  if (opts.endpoint) sp.set('endpoint', opts.endpoint);
  if (opts.userId) sp.set('user_id', opts.userId);
  if (opts.status) sp.set('status', opts.status);
  const qs = sp.toString();
  return getJson<AiCallRow[]>(`/api/admin/ai/calls${qs ? `?${qs}` : ''}`);
}

export function fetchAiCallDetail(callId: number): Promise<AiCallDetail> {
  return getJson<AiCallDetail>(`/api/admin/ai/calls/${callId}`);
}

export function fetchGroundingRate(periodHours: 1 | 24 | 168 = 24): Promise<GroundingRate> {
  return getJson<GroundingRate>(`/api/admin/ai/grounding-rate?period_hours=${periodHours}`);
}

export async function triggerMorningBrief(): Promise<void> {
  const res = await fetch('/api/ai/morning-brief', { method: 'POST', credentials: 'include' });
  if (!res.ok) throw new Error(`morning-brief failed: ${res.status}`);
}

export async function triggerInsightsScan(): Promise<void> {
  const res = await fetch('/api/ai/insights/scan-now', { method: 'POST', credentials: 'include' });
  if (!res.ok) throw new Error(`insights scan failed: ${res.status}`);
}
