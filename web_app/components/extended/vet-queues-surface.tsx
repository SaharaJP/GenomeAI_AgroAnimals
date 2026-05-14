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
    <div className="topbar"><div><h1 className="page-title">Ветеринария</h1><p className="page-subtitle">Очереди задач ветеринарной службы: здоровье животных, осмотры и история решений.</p></div></div>
    <FactPackGuardrailNote />
    <ExplainabilityBlock title="Источник данных" reasons={[
      'Группировка очередей — по типу задачи, домену здоровья и серьёзности алерта (данные с сервера).',
      'Браузер не создаёт факторы здоровья — только отображает привязку к причинам с бэкенда.',
      'Диагностика, история решений и хуки поддержки управляются сервером.',
    ]} />
    {error ? <div className="card error-text">{error}</div> : null}
    {!view ? <div className="card">Загрузка ветеринарных очередей…</div> : <>
      <div className="grid grid-3">
        <MetricCard title="Задач в очереди" value={view.summary.queueItems} />
        <MetricCard title="Просрочено" value={view.summary.overdueItems} />
        <MetricCard title="Критические алерты" value={view.summary.highSeverityAlerts} />
      </div>
      <div className="grid grid-2">
        <ScopeSummary scope={view.scope} />
        <Card>
          <h3 className="card-title">Связанные действия</h3>
          <div className="linked-inline-actions">
            <Link href="/copilot?target=vet">Объяснить в ИИ-помощнике</Link>
            <Link href="/decisions?queue=vet">История решений</Link>
            <Link href="/vet?tab=withdrawal">Лечение / каренция</Link>
            <Link href="/support?context=vet">Поддержка / диагностика</Link>
          </div>
          <p className="small-muted" style={{ marginTop: 12 }}>{view.parityNote}</p>
        </Card>
      </div>
      <div className="grid grid-2">
        <div><h2 className="section-title">Ветеринарные алерты</h2><AlertList items={view.alerts} /></div>
        <div><h2 className="section-title">Ветеринарные задачи</h2><WorklistList items={view.worklists} /></div>
      </div>
    </>}</div>;
}
