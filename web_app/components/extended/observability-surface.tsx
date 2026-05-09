'use client';
import Link from 'next/link';
import { useEffect, useState } from 'react';
import { Card, MetricCard } from '@/components/ui/card';
import { fetchExtendedBundle } from '@/lib/api/extended-surfaces';

export function ObservabilitySurface() {
  const [payload, setPayload] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    void fetchExtendedBundle().then((bundle) => {
      if (active) setPayload(bundle.observability);
    }).catch((err) => {
      if (active) setError(err instanceof Error ? err.message : 'Failed to load observability surface');
    });
    return () => { active = false; };
  }, []);

  const requests = Number((payload as { requests_total?: number })?.requests_total || (payload as { requests?: number })?.requests || 0);
  const jobs = Number((payload as { jobs_total?: number })?.jobs_total || (payload as { jobs?: number })?.jobs || 0);
  const audits = Number((payload as { audit_total?: number })?.audit_total || (payload as { audit?: number })?.audit || 0);

  return <div className="grid">
    <div className="topbar"><div><h1 className="page-title">Observability</h1><p className="page-subtitle">Diagnostics and runtime telemetry surface routed through backend evidence.</p></div></div>
    {error ? <div className="card error-text">{error}</div> : null}
    {!payload ? <div className="card">Loading observability…</div> : <>
      <div className="grid grid-3">
        <MetricCard title="Requests" value={requests} />
        <MetricCard title="Jobs" value={jobs} />
        <MetricCard title="Audit events" value={audits} />
      </div>
      <Card>
        <h3 className="card-title">Diagnostics hooks</h3>
        <div className="linked-inline-actions">
          <Link href="/support">Support</Link>
          <Link href="/readiness">Readiness</Link>
          <Link href="/admin">Admin</Link>
          <Link href="/analytics?tab=reports">Reports</Link>
        </div>
        <pre style={{ whiteSpace: 'pre-wrap', marginTop: 12 }}>{JSON.stringify(payload, null, 2)}</pre>
      </Card>
    </>}</div>;
}
