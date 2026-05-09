'use client';
import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { Card, MetricCard } from '@/components/ui/card';
import { FactPackGuardrailNote } from '@/components/explainability/fact-pack-guardrail-note';
import { SourceLinkagePanel } from '@/components/explainability/source-linkage-panel';
import { ObjectExplainabilityPanel } from '@/components/explainability/object-explainability-panel';
import { AssistantEntryPoints } from '@/components/assistant/assistant-entry-points';
import { DecisionIntelligenceWidgets } from '@/components/decision/decision-intelligence-widgets';
import { ReportGovernancePanel } from '@/components/analytics/reports/report-governance-panel';
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
        setError(err instanceof Error ? err.message : 'Ошибка загрузки отчёта');
      });
    return () => {
      active = false;
    };
  }, [dataVersion, reportVersion]);

  const permissions = useMemo(() => new Set(me?.user.permissions || []), [me]);
  const canApprove = permissions.has('reports.approve') || permissions.has('reports.approve_all') || permissions.has('reports.review');
  const canArchive = permissions.has('reports.archive');
  const linkageSummary = [
    { label: 'Версия данных', value: dataVersion },
    { label: 'Версия отчёта', value: reportVersion },
    { label: 'Статус утверждения', value: approval?.status || status || 'черновик' },
    { label: 'Кем обновлено', value: approval?.updated_by_username || '—' },
  ];

  return (
    <div className="grid">
      <div className="topbar">
        <div>
          <h1 className="page-title">Просмотр отчёта</h1>
          <p className="page-subtitle">Детали отчёта, привязка к источникам, управление и точки входа в ассистента.</p>
        </div>
      </div>
      <FactPackGuardrailNote />
      {error ? <div className="card error-text">{error}</div> : null}
      <div className="grid grid-3">
        <MetricCard title="Версия отчёта" value={reportVersion} />
        <MetricCard title="Версия данных" value={dataVersion} />
        <MetricCard title="Текущий статус" value={approval?.status || status} />
      </div>
      <div className="grid grid-2">
        <SourceLinkagePanel items={linkageSummary} />
        <AssistantEntryPoints dataVersion={dataVersion} reportVersion={reportVersion} contextLabel="report_view" />
      </div>
      <ObjectExplainabilityPanel
        title="Объяснимость отчёта"
        reasons={[
          { title: 'Только fact-pack', detail: 'Интерпретация отчёта ограничена привязкой версий и гарантиями бэкенда.', source: 'decision' },
          { title: 'Привязка источников', detail: 'Каждое действие с отчётом привязано к версии, а не выведено из состояния фронтенда.', source: 'worklist' },
          { title: 'Без изобретённых факторов', detail: 'React не создаёт новых факторов или объяснений содержимого отчёта.', source: 'alert' },
        ]}
      />
      <Card>
        <h3 className="card-title">Связанные действия</h3>
        <div className="linked-inline-actions">
          <Link href={`/assistant?target=report&data_version=${encodeURIComponent(dataVersion)}&report_version=${encodeURIComponent(reportVersion)}`}>Объяснить в ассистенте</Link>
          <Link href={`/decisions?report_version=${encodeURIComponent(reportVersion)}`}>Решение</Link>
          <Link href={`/support?report_version=${encodeURIComponent(reportVersion)}`}>Обратная связь / поддержка</Link>
          <Link href="/analytics?tab=reports">К каталогу отчётов</Link>
        </div>
        {comment ? <p className="small-muted" style={{ marginTop: 12 }}>Комментарий каталога: {comment}</p> : null}
      </Card>
      <ReportGovernancePanel dataVersion={dataVersion} reportVersion={reportVersion} approval={approval} canApprove={canApprove} canArchive={canArchive} />
      {decisionIntel ? <DecisionIntelligenceWidgets data={decisionIntel} /> : null}
    </div>
  );
}
