'use client';
import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { Card, MetricCard } from '@/components/ui/card';
import { FactPackGuardrailNote } from '@/components/explainability/fact-pack-guardrail-note';
import { SourceLinkagePanel } from '@/components/explainability/source-linkage-panel';
import { ObjectExplainabilityPanel } from '@/components/explainability/object-explainability-panel';
import { AssistantEntryPoints } from '@/components/assistant/assistant-entry-points';
import { DecisionIntelligenceWidgets } from '@/components/decision/decision-intelligence-widgets';
import { ReportGovernancePanel } from '@/components/reports/report-governance-panel';
import { fetchDecisionIntelligence, fetchFeedbackFeed, fetchReportsCatalog, type ReportApprovalState } from '@/lib/api/profiles-reports-assistant';
import { authFetch } from '@/lib/api/client';
import type { AuthMeResponse, DecisionIntelligenceResponse } from '@/lib/api/contracts';

export function ReportViewSurface({ dataVersion, reportVersion }: { dataVersion: string; reportVersion: string }) {
  const [me, setMe] = useState<AuthMeResponse | null>(null);
  const [decisionIntel, setDecisionIntel] = useState<DecisionIntelligenceResponse | null>(null);
  const [approval, setApproval] = useState<ReportApprovalState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [comment, setComment] = useState<string | null>(null);
  const [status, setStatus] = useState<string>('unknown');

  useEffect(() => {
    let active = true;
    setError(null);
    void Promise.all([
      authFetch<AuthMeResponse>('/me'),
      fetchDecisionIntelligence(),
      fetchFeedbackFeed(),
      fetchReportsCatalog(),
      fetch(`/api/report-governance/${encodeURIComponent(dataVersion)}/${encodeURIComponent(reportVersion)}`, { cache: 'no-store' }).then(async (response) => {
        const body = await response.json();
        if (!response.ok) throw new Error(body?.detail || 'Failed to load governance');
        return body as { approval: ReportApprovalState };
      }),
    ])
      .then(([mePayload, decisionPayload, feedbackPayload, reportCatalog, governance]) => {
        if (!active) return;
        setMe(mePayload);
        setDecisionIntel(decisionPayload);
        const report = reportCatalog.items.find((item) => item.data_version === dataVersion && item.report_version === reportVersion);
        setStatus(report?.status || governance.approval?.status || 'draft');
        setComment(report?.comment || governance.approval?.comment || null);
        setApproval(governance.approval || null);
      })
      .catch((err) => {
        if (!active) return;
        setError(err instanceof Error ? err.message : 'Failed to load report view');
      });
    return () => {
      active = false;
    };
  }, [dataVersion, reportVersion]);

  const permissions = useMemo(() => new Set(me?.user.permissions || []), [me]);
  const canApprove = permissions.has('reports.approve') || permissions.has('reports.approve_all') || permissions.has('reports.review');
  const canArchive = permissions.has('reports.archive');
  const linkageSummary = [
    { label: 'Data version', value: dataVersion },
    { label: 'Report version', value: reportVersion },
    { label: 'Approval status', value: approval?.status || status || 'draft' },
    { label: 'Updated by', value: approval?.updated_by_username || '—' },
  ];

  return (
    <div className="grid">
      <div className="topbar">
        <div>
          <h1 className="page-title">Report View</h1>
          <p className="page-subtitle">Report detail, source linkage, governance hooks and assistant entry points in the new React shell.</p>
        </div>
      </div>
      <FactPackGuardrailNote />
      {error ? <div className="card error-text">{error}</div> : null}
      <div className="grid grid-3">
        <MetricCard title="Report version" value={reportVersion} />
        <MetricCard title="Data version" value={dataVersion} />
        <MetricCard title="Current status" value={approval?.status || status} />
      </div>
      <div className="grid grid-2">
        <SourceLinkagePanel items={linkageSummary} />
        <AssistantEntryPoints dataVersion={dataVersion} reportVersion={reportVersion} contextLabel="report_view" />
      </div>
      <ObjectExplainabilityPanel
        title="Report explainability posture"
        reasons={[
          { title: 'Fact-pack only', detail: 'Report interpretation must stay bounded by report_version/data_version linkage and backend guardrails.', source: 'decision' },
          { title: 'Source linkage', detail: 'Every report action remains tied to version linkage rather than inferred frontend state.', source: 'worklist' },
          { title: 'No invented factors', detail: 'React does not create new factors or explanations for report content.', source: 'alert' },
        ]}
      />
      <Card>
        <h3 className="card-title">Linked actions</h3>
        <div className="linked-inline-actions">
          <Link href={`/assistant?target=report&data_version=${encodeURIComponent(dataVersion)}&report_version=${encodeURIComponent(reportVersion)}`}>Explain in assistant</Link>
          <Link href={`/decisions?report_version=${encodeURIComponent(reportVersion)}`}>Decision hook</Link>
          <Link href={`/support?report_version=${encodeURIComponent(reportVersion)}`}>Feedback / support hook</Link>
          <Link href="/reports">Back to report catalog</Link>
        </div>
        {comment ? <p className="small-muted" style={{ marginTop: 12 }}>Catalog comment: {comment}</p> : null}
      </Card>
      <ReportGovernancePanel dataVersion={dataVersion} reportVersion={reportVersion} approval={approval} canApprove={canApprove} canArchive={canArchive} />
      {decisionIntel ? <DecisionIntelligenceWidgets data={decisionIntel} /> : null}
    </div>
  );
}
