'use client';
import Link from 'next/link';
import { useEffect, useState } from 'react';
import { AlertList } from '@/components/operations/alert-list';
import { ScopeSummary } from '@/components/operations/scope-summary';
import { Card, MetricCard } from '@/components/ui/card';
import { WorklistList } from '@/components/ui/worklist-list';
import { ExplainabilityBlock } from '@/components/ui/explainability-block';
import { FactPackGuardrailNote } from '@/components/explainability/fact-pack-guardrail-note';
import { fetchExtendedBundle, buildVetViewModel, type VetViewModel } from '@/lib/api/extended-surfaces';

export function VetQueuesSurface() {
  const [view, setView] = useState<VetViewModel | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    void fetchExtendedBundle().then((bundle) => {
      if (active) setView(buildVetViewModel(bundle));
    }).catch((err) => {
      if (active) setError(err instanceof Error ? err.message : 'Failed to load vet queue surface');
    });
    return () => { active = false; };
  }, []);

  return <div className="grid">
    <div className="topbar"><div><h1 className="page-title">Vet queues</h1><p className="page-subtitle">Office-grade triage surface for vet teams, health follow-ups and linked decision evidence.</p></div></div>
    <FactPackGuardrailNote />
    <ExplainabilityBlock title="Queue evidence" reasons={[
      'Queue grouping uses backend worklist_type, health domain and alert severity fields.',
      'React does not create health factors; it only shows backend why/reason linkage.',
      'Diagnostics, decision trail and support hooks stay server-governed.',
    ]} />
    {error ? <div className="card error-text">{error}</div> : null}
    {!view ? <div className="card">Loading vet queues…</div> : <>
      <div className="grid grid-3">
        <MetricCard title="Queue items" value={view.summary.queueItems} />
        <MetricCard title="Overdue items" value={view.summary.overdueItems} />
        <MetricCard title="High severity alerts" value={view.summary.highSeverityAlerts} />
      </div>
      <div className="grid grid-2">
        <ScopeSummary scope={view.scope} />
        <Card>
          <h3 className="card-title">Linked actions</h3>
          <div className="linked-inline-actions">
            <Link href="/assistant?target=vet">Explain in assistant</Link>
            <Link href="/decisions?queue=vet">Decision trail</Link>
            <Link href="/treatments">Treatments / withdrawal</Link>
            <Link href="/support?context=vet">Support / diagnostics</Link>
          </div>
          <p className="small-muted" style={{ marginTop: 12 }}>{view.parityNote}</p>
        </Card>
      </div>
      <div className="grid grid-2">
        <div><h2 className="section-title">Vet alerts</h2><AlertList items={view.alerts} /></div>
        <div><h2 className="section-title">Vet worklists</h2><WorklistList items={view.worklists} /></div>
      </div>
    </>}</div>;
}
