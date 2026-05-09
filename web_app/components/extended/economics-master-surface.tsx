'use client';
import Link from 'next/link';
import { useEffect, useState } from 'react';
import { Card, MetricCard } from '@/components/ui/card';
import { DataTable } from '@/components/ui/data-table';
import { ScopeSummary } from '@/components/operations/scope-summary';
import { fetchExtendedBundle, buildEconomicsViewModel, type EconomicsViewModel } from '@/lib/api/extended-surfaces';

const DEFAULT_DATA_VERSION = 'dv_demo_farm_v1';

function firstReportDataVersion(items: Array<Record<string, unknown>>): string | null {
  for (const item of items) {
    const value = typeof item.data_version === 'string' ? item.data_version.trim() : '';
    if (value) return value;
  }
  return null;
}

function buildEconomicsAssistantHref(view: EconomicsViewModel): string {
  const scenarioWithDataVersion = view.scenarios.find((item) => String((item as Record<string, unknown>).data_version || '').trim());
  const scenarioDataVersion =
    typeof (scenarioWithDataVersion as Record<string, unknown> | undefined)?.data_version === 'string'
      ? String((scenarioWithDataVersion as Record<string, unknown>).data_version).trim()
      : '';
  const dataVersion = scenarioDataVersion || firstReportDataVersion(view.reportItems as Array<Record<string, unknown>>) || DEFAULT_DATA_VERSION;
  const target = `genomeai://copilot/fact?data_version=${encodeURIComponent(dataVersion)}&section=modules.economics&table=summary_farm_top`;
  return `/copilot?data_version=${encodeURIComponent(dataVersion)}&target=${encodeURIComponent(target)}`;
}

export function EconomicsMasterSurface() {
  const [view, setView] = useState<EconomicsViewModel | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    void fetchExtendedBundle().then((bundle) => {
      if (active) setView(buildEconomicsViewModel(bundle));
    }).catch((err) => {
      if (active) setError(err instanceof Error ? err.message : 'Failed to load economics surface');
    });
    return () => { active = false; };
  }, []);

  return <div className="grid">
    <div className="topbar"><div><h1 className="page-title">Economics / what-if</h1><p className="page-subtitle">Economics parity surface for scenarios, scenario-backed reports and office decision review.</p></div></div>
    {error ? <div className="card error-text">{error}</div> : null}
    {!view ? <div className="card">Loading economics…</div> : <>
      <div className="grid grid-3">
        <MetricCard title="Scenarios" value={view.summary.scenariosTotal} />
        <MetricCard title="Reports" value={view.summary.reportsTotal} />
        <MetricCard title="Decision acceptance" value={`${Math.round(view.summary.decisionAcceptanceRate * 100)}%`} />
      </div>
      <div className="grid grid-2">
        <ScopeSummary scope={view.scope} />
        <Card>
          <h3 className="card-title">Linked office flows</h3>
          <div className="linked-inline-actions">
            <Link href="/analytics">Open reports</Link>
            {view ? <Link href={buildEconomicsAssistantHref(view)}>Explain in assistant</Link> : <Link href="/copilot">Explain in assistant</Link>}
            <Link href="/decisions?context=economics">Decision trail</Link>
            <Link href="/support?context=economics">Support / pilot evidence</Link>
          </div>
          <p className="small-muted" style={{ marginTop: 12 }}>Economics calculations remain backend-only; React renders scenarios and governance evidence without reimplementing formulas.</p>
        </Card>
      </div>
      <DataTable rows={view.scenarios} columns={[
        { key: 'name', header: 'Scenario', render: (row) => row.name || row.scenario_id },
        { key: 'status', header: 'Status', render: (row) => row.status },
        { key: 'report_version', header: 'Report version', render: (row) => row.report_version || '—' },
        { key: 'data_version', header: 'Data version', render: (row) => row.data_version || '—' },
      ]} />
    </>}</div>;
}
