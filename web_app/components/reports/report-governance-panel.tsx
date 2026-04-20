'use client';
import { useState } from 'react';
import { Card } from '@/components/ui/card';
import type { ReportApprovalState } from '@/lib/api/profiles-reports-assistant';

async function updateGovernance(dataVersion: string, reportVersion: string, action: 'approve' | 'reject' | 'archive', comment: string) {
  const response = await fetch(`/api/report-governance/${encodeURIComponent(dataVersion)}/${encodeURIComponent(reportVersion)}`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ action, comment }),
  });
  const body = await response.json();
  if (!response.ok) throw new Error(body?.detail || body?.error || 'Governance action failed');
  return body as { ok: boolean; approval: ReportApprovalState };
}

export function ReportGovernancePanel({
  dataVersion,
  reportVersion,
  approval,
  canApprove,
  canArchive,
}: {
  dataVersion: string;
  reportVersion: string;
  approval: ReportApprovalState | null;
  canApprove: boolean;
  canArchive: boolean;
}) {
  const [state, setState] = useState<ReportApprovalState | null>(approval);
  const [comment, setComment] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  async function run(action: 'approve' | 'reject' | 'archive') {
    try {
      setBusy(action);
      setError(null);
      const result = await updateGovernance(dataVersion, reportVersion, action, comment);
      setState(result.approval || null);
      setComment('');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Governance action failed');
    } finally {
      setBusy(null);
    }
  }

  return (
    <Card>
      <h3 className="card-title">Report governance</h3>
      <div className="meta-list">
        <div className="meta-row"><span>Status</span><strong>{state?.status || 'draft'}</strong></div>
        <div className="meta-row"><span>Updated at</span><strong>{state?.updated_at || '—'}</strong></div>
        <div className="meta-row"><span>Updated by</span><strong>{state?.updated_by_username || '—'}</strong></div>
      </div>
      <p className="small-muted" style={{ marginTop: 12 }}>Governance actions stay server-owned and audited. React only forwards the requested action.</p>
      <textarea className="input" style={{ width: '100%', minHeight: 92, marginTop: 12 }} value={comment} onChange={(e: { target: { value: string } }) => setComment(e.target.value)} placeholder="Optional governance comment" />
      {error ? <div className="error-text" style={{ marginTop: 10 }}>{error}</div> : null}
      <div className="toolbar" style={{ marginTop: 12 }}>
        {canApprove ? <button className="button" disabled={busy !== null} onClick={() => void run('approve')}>{busy === 'approve' ? 'Approving…' : 'Approve'}</button> : null}
        {canApprove ? <button className="button button-secondary" disabled={busy !== null} onClick={() => void run('reject')}>{busy === 'reject' ? 'Rejecting…' : 'Reject'}</button> : null}
        {canArchive ? <button className="button button-danger" disabled={busy !== null} onClick={() => void run('archive')}>{busy === 'archive' ? 'Archiving…' : 'Archive'}</button> : null}
      </div>
    </Card>
  );
}
