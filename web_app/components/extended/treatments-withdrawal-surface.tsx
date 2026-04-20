'use client';
import Link from 'next/link';
import { useEffect, useState } from 'react';
import { AlertList } from '@/components/operations/alert-list';
import { ScopeSummary } from '@/components/operations/scope-summary';
import { Card, MetricCard } from '@/components/ui/card';
import { WorklistList } from '@/components/ui/worklist-list';
import { FactPackGuardrailNote } from '@/components/explainability/fact-pack-guardrail-note';
import { fetchExtendedBundle, buildTreatmentViewModel, type TreatmentViewModel } from '@/lib/api/extended-surfaces';

export function TreatmentsWithdrawalSurface() {
  const [view, setView] = useState<TreatmentViewModel | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    void fetchExtendedBundle().then((bundle) => {
      if (active) setView(buildTreatmentViewModel(bundle));
    }).catch((err) => {
      if (active) setError(err instanceof Error ? err.message : 'Failed to load treatments surface');
    });
    return () => { active = false; };
  }, []);

  return <div className="grid">
    <div className="topbar"><div><h1 className="page-title">Treatments / withdrawal</h1><p className="page-subtitle">Governed treatment and withdrawal watch surface driven by backend health evidence.</p></div></div>
    <FactPackGuardrailNote />
    {error ? <div className="card error-text">{error}</div> : null}
    {!view ? <div className="card">Loading treatments / withdrawal…</div> : <>
      <div className="grid grid-3">
        <MetricCard title="Treatment tasks" value={view.summary.treatmentTasks} />
        <MetricCard title="Withdrawal watch" value={view.summary.withdrawalWatch} />
        <MetricCard title="Diagnostics available" value={view.summary.diagnosticsAvailable} />
      </div>
      <div className="grid grid-2">
        <ScopeSummary scope={view.scope} />
        <Card>
          <h3 className="card-title">Governance and evidence</h3>
          <ul className="bullet-list compact">{view.rulesEvidence.map((item) => <li key={item}>{item}</li>)}</ul>
          <div className="linked-inline-actions">
            <Link href="/vet">Open vet queues</Link>
            <Link href="/assistant?target=treatments">Explain in assistant</Link>
            <Link href="/reports">Report / export</Link>
            <Link href="/support?context=treatments">Support / diagnostics</Link>
          </div>
          <p className="small-muted" style={{ marginTop: 12 }}>{view.parityNote}</p>
        </Card>
      </div>
      <div className="grid grid-2">
        <div><h2 className="section-title">Withdrawal / treatment alerts</h2><AlertList items={view.alerts} /></div>
        <div><h2 className="section-title">Treatment-linked worklists</h2><WorklistList items={view.worklists} /></div>
      </div>
    </>}</div>;
}
