'use client';
import Link from 'next/link';
import { useEffect, useState } from 'react';
import { Card, MetricCard } from '@/components/ui/card';
import { fetchExtendedBundle } from '@/lib/api/extended-surfaces';
import type { SupportResponse } from '@/lib/api/contracts';

export function SupportGovernanceSurface({ hookContext }: { hookContext?: Record<string, string | undefined> }) {
  const [support, setSupport] = useState<SupportResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    void fetchExtendedBundle().then((bundle) => {
      if (active) setSupport(bundle.support);
    }).catch((err) => {
      if (active) setError(err instanceof Error ? err.message : 'Failed to load support surface');
    });
    return () => { active = false; };
  }, []);

  const summary = support?.summary;
  return <div className="grid">
    {hookContext && Object.keys(hookContext).length > 0 ? <Card><h3 className="card-title">Support hook context</h3><pre style={{ whiteSpace: 'pre-wrap', margin: 0 }}>{JSON.stringify(hookContext, null, 2)}</pre></Card> : null}
    {error ? <div className="card error-text">{error}</div> : null}
    {!support ? <div className="card">Loading support…</div> : <>
      <div className="grid grid-3">
        <MetricCard title="Open incidents" value={summary?.open_incidents || 0} />
        <MetricCard title="Critical incidents" value={summary?.critical_open_incidents || 0} />
        <MetricCard title="Support bundles" value={summary?.support_bundle_count || 0} />
      </div>
      <Card>
        <h3 className="card-title">Governance flows</h3>
        <div className="linked-inline-actions">
          <Link href="/observability">Observability</Link>
          <Link href="/readiness">Readiness</Link>
          <Link href="/pilot">Pilot</Link>
          <Link href="/admin">Admin</Link>
        </div>
        <pre style={{ whiteSpace: 'pre-wrap', marginTop: 12 }}>{JSON.stringify(support, null, 2)}</pre>
      </Card>
    </>}</div>;
}
