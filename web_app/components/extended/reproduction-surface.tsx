'use client';
import Link from 'next/link';
import { useEffect, useState } from 'react';
import { Card, MetricCard } from '@/components/ui/card';
import { AlertList } from '@/components/operations/alert-list';
import { WorklistList } from '@/components/ui/worklist-list';
import { ScopeSummary } from '@/components/operations/scope-summary';
import { FactPackGuardrailNote } from '@/components/explainability/fact-pack-guardrail-note';
import { ExplainabilityBlock } from '@/components/ui/explainability-block';
import { fetchExtendedBundle, buildReproductionViewModel, type ReproductionViewModel } from '@/lib/api/extended-surfaces';

export function ReproductionSurface() {
  const [view, setView] = useState<ReproductionViewModel | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    void fetchExtendedBundle()
      .then((bundle) => {
        if (active) setView(buildReproductionViewModel(bundle));
      })
      .catch((err) => {
        if (active) setError(err instanceof Error ? err.message : 'Failed to load reproduction surface');
      });
    return () => {
      active = false;
    };
  }, []);

  return (
    <div className="grid">
      <div className="topbar"><div><h1 className="page-title">Reproduction</h1><p className="page-subtitle">Operational reproduction parity in React for office and herd-management workflows.</p></div></div>
      <FactPackGuardrailNote />
      <ExplainabilityBlock title="Parity posture" reasons={[
        'React reads backend worklist_type=reproduction, repro domain fields and planner approvals only.',
        'No reproduction logic is reimplemented in the browser.',
        'Linked actions keep decision, assistant and report lineage intact.',
      ]} />
      {error ? <div className="card error-text">{error}</div> : null}
      {!view ? <div className="card">Loading reproduction surface…</div> : (
        <>
          <div className="grid grid-3">
            <MetricCard title="Open repro worklists" value={view.summary.openWorklists} />
            <MetricCard title="Overdue repro worklists" value={view.summary.overdueWorklists} />
            <MetricCard title="Pending approvals" value={view.summary.pendingApprovals} />
          </div>
          <div className="grid grid-2">
            <ScopeSummary scope={view.scope} />
            <Card>
              <h3 className="card-title">Linked actions</h3>
              <p className="card-subtitle">Keep planner, reports and explainability hooks connected to the same backend evidence.</p>
              <div className="linked-inline-actions">
                <Link href="/planner">Open planner</Link>
                <Link href="/assistant?target=repro">Explain in assistant</Link>
                <Link href="/reports">Open reports</Link>
                <Link href="/support?context=reproduction">Support / feedback</Link>
              </div>
              <p className="small-muted" style={{ marginTop: 12 }}>{view.parityNote}</p>
            </Card>
          </div>
          <div className="grid grid-2">
            <div>
              <h2 className="section-title">Reproduction alerts</h2>
              <AlertList items={view.alerts} />
            </div>
            <div>
              <h2 className="section-title">Reproduction worklists</h2>
              <WorklistList items={view.worklists} />
            </div>
          </div>
          <Card>
            <h3 className="card-title">Planner preview</h3>
            {view.planPreview.length === 0 ? <p className="small-muted">No weekly plans available for the current scope.</p> : (
              <div className="grid">
                {view.planPreview.map((plan) => (
                  <div className="linked-action-card" key={plan.plan_id}>
                    <div className="linked-action-count">{plan.item_count}</div>
                    <div>
                      <div className="linked-action-title">{plan.name}</div>
                      <div className="linked-action-caption">week_start={plan.week_start} · farm={plan.farm_id || 'all'} · approvals={plan.approved_at ? 'approved' : 'pending'}</div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Card>
        </>
      )}
    </div>
  );
}
