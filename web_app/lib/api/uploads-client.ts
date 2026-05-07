export interface UploadColumnSpec {
  name: string;
  required: boolean;
  kind: string;
  description: string;
  min_val?: number | null;
  max_val?: number | null;
  fk_table?: string | null;
}

export interface UploadTypeMeta {
  type: string;
  label: string;
  target_table: string;
  instructions: string;
  columns: UploadColumnSpec[];
}

export interface UploadRowError {
  row: number;
  field?: string | null;
  message: string;
}

export interface UploadPreviewResponse {
  type: string;
  total_rows: number;
  valid: number;
  duplicates: number;
  errors: UploadRowError[];
  preview_token: string;
  valid_rows_sample: Record<string, unknown>[];
}

export interface UploadCommitResponse {
  inserted: number;
  skipped_duplicates: number;
}

export async function fetchUploadTypes(): Promise<{ items: UploadTypeMeta[] }> {
  const r = await fetch('/api/uploads/types', { cache: 'no-store' });
  if (!r.ok) throw new Error(`fetchUploadTypes ${r.status}`);
  return r.json();
}

export function templateUrl(type: string, fmt: 'csv' | 'xlsx'): string {
  const qs = new URLSearchParams({ type, fmt });
  return `/api/uploads/template?${qs.toString()}`;
}

export async function postPreview(type: string, file: File): Promise<UploadPreviewResponse> {
  const fd = new FormData();
  fd.append('file', file);
  const qs = new URLSearchParams({ type });
  const r = await fetch(`/api/uploads/preview?${qs.toString()}`, {
    method: 'POST', body: fd,
  });
  if (!r.ok) throw new Error(`postPreview ${r.status}`);
  return r.json();
}

export async function postCommit(token: string): Promise<UploadCommitResponse> {
  const r = await fetch('/api/uploads/commit', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ preview_token: token }),
  });
  if (r.status === 410) throw new Error('token_expired');
  if (!r.ok) throw new Error(`postCommit ${r.status}`);
  return r.json();
}
