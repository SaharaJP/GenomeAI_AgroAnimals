import { apiFetch } from '@/lib/api/client';

export type AuditRow = {
  id: number;
  ts: string;
  username: string | null;
  role: string | null;
  action: string;
  status: string | null;
  object_type: string | null;
  object_id: string | null;
  before_json: string | null;
  after_json: string | null;
  error: string | null;
  request_id: string | null;
};

export type AuditListResponse = {
  rows: AuditRow[];
  filters: Record<string, string | null>;
  schema_version: number;
  facets: unknown;
};

export type AuditFilters = {
  object_id?: string;
  object_type?: string;
  action?: string;
  action_prefix?: string;
  username?: string;
  q?: string;
  limit?: number;
};

export async function listAudit(filters: AuditFilters = {}): Promise<AuditListResponse> {
  const params = new URLSearchParams();
  for (const [k, v] of Object.entries(filters)) {
    if (v !== undefined && v !== null && String(v).length > 0) {
      params.set(k, String(v));
    }
  }
  const qs = params.toString();
  const path = `/api/audit${qs ? `?${qs}` : ''}`;
  return apiFetch<AuditListResponse>(path);
}
