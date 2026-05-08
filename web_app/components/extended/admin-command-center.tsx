'use client';
import Link from 'next/link';
import { useEffect, useState } from 'react';
import { Card, MetricCard } from '@/components/ui/card';
import { ScopeSummary } from '@/components/operations/scope-summary';
import { DataTable } from '@/components/ui/data-table';
import { fetchExtendedBundle, buildAdminViewModel, type AdminViewModel } from '@/lib/api/extended-surfaces';

export function AdminCommandCenter() {
  const [view, setView] = useState<AdminViewModel | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    void fetchExtendedBundle().then((bundle) => {
      if (active) setView(buildAdminViewModel(bundle));
    }).catch((err) => {
      if (active) setError(err instanceof Error ? err.message : 'Failed to load admin command center');
    });
    return () => { active = false; };
  }, []);

  const rows = view && Array.isArray((view.permissionMatrix as { rows?: Array<Record<string, unknown>> }).rows)
    ? ((view.permissionMatrix as { rows?: Array<Record<string, unknown>> }).rows || []).slice(0, 12)
    : [];

  return <div className="grid">
    <div className="topbar"><div><h1 className="page-title">Admin / master system</h1><p className="page-subtitle">Enterprise admin surface for permissions, diagnostics, readiness and pilot evidence.</p></div></div>
    {error ? <div className="card error-text">{error}</div> : null}
    {!view ? <div className="card">Loading admin command center…</div> : <>
      <div className="grid grid-3">
        <MetricCard title="Role rows" value={view.summary.roleCount} />
        <MetricCard title="Permission rows" value={view.summary.permissionRows} />
        <MetricCard title="Readiness checks" value={view.summary.readinessChecks} />
      </div>
      <div className="grid grid-2">
        <ScopeSummary scope={view.scope} />
        <Card>
          <h3 className="card-title">Admin flows</h3>
          <div className="linked-inline-actions">
            <Link href="/admin/ai">AI-наблюдаемость</Link>
            <Link href="/observability">Observability</Link>
            <Link href="/support">Support</Link>
            <Link href="/pilot">Pilot</Link>
            <Link href="/readiness">Readiness</Link>
          </div>
          <p className="small-muted" style={{ marginTop: 12 }}>Admin surface stays server-backed: permission matrix, diagnostics and readiness all come from backend evidence, not frontend shortcuts.</p>
        </Card>
      </div>
      <Card>
        <h3 className="card-title">Permission matrix preview</h3>
        {rows.length === 0 ? <p className="small-muted">Permission matrix preview is unavailable in this environment.</p> : <DataTable rows={rows} columns={[
          { key: 'role', header: 'Role', render: (row) => String((row as Record<string, unknown>).role || '—') },
          { key: 'permission', header: 'Permission', render: (row) => String((row as Record<string, unknown>).permission || '—') },
          { key: 'source', header: 'Source', render: (row) => String((row as Record<string, unknown>).source || '—') },
        ]} />}
      </Card>
    </>}</div>;
}
