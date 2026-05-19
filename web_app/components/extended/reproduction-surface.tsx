'use client';
import Link from 'next/link';
import { useEffect, useState } from 'react';
import { Card, MetricCard } from '@/components/ui/card';
import { AlertList } from '@/components/operations/alert-list';
import { WorklistList } from '@/components/ui/worklist-list';
import { ScopeSummary } from '@/components/operations/scope-summary';
import { FactPackGuardrailNote } from '@/components/explainability/fact-pack-guardrail-note';
import { ExplainabilityBlock } from '@/components/ui/explainability-block';
import { LoaderWithRetry } from '@/components/ui/loader-with-retry';
import { fetchExtendedBundle, buildReproductionViewModel, type ReproductionViewModel } from '@/lib/api/extended-surfaces';

export function ReproductionSurface() {
  const [view, setView] = useState<ReproductionViewModel | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reloadTick, setReloadTick] = useState(0);

  useEffect(() => {
    let active = true;
    setView(null);
    setError(null);
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
  }, [reloadTick]);

  const retry = () => setReloadTick((n) => n + 1);

  return (
    <div className="grid">
      <div className="topbar"><div><h1 className="page-title">Воспроизводство</h1><p className="page-subtitle">Оперативное управление воспроизводством стада: рабочие списки, алерты и планы.</p></div></div>
      <FactPackGuardrailNote />
      {/* No reproduction logic is reimplemented in the browser — surface is read-only and reads from the canonical reproduction API. */}
      <ExplainabilityBlock title="Источник данных" reasons={[
        'Данные читаются с бэкенда: тип задачи reproduction, поля репродуктивного домена и согласования планировщика.',
        'Логика воспроизводства не переносится в браузер — только отображение.',
        'Связанные действия сохраняют привязку к решениям, помощнику и отчётам.',
      ]} />
      {!view || error ? (
        <LoaderWithRetry label="Загрузка данных воспроизводства…" error={error} onRetry={retry} />
      ) : (
        <>
          <div className="grid grid-3">
            <MetricCard title="Открытые задачи" value={view.summary.openWorklists} />
            <MetricCard title="Просроченные" value={view.summary.overdueWorklists} />
            <MetricCard title="Ожидают согласования" value={view.summary.pendingApprovals} />
          </div>
          <div className="grid grid-2">
            <ScopeSummary scope={view.scope} />
            <Card>
              <h3 className="card-title">Связанные действия</h3>
              <p className="card-subtitle">Планировщик, отчёты и объяснения привязаны к одной доказательной базе.</p>
              <div className="linked-inline-actions">
                <Link href="/timeline">Открыть планировщик</Link>
                <Link href="/copilot?target=repro">Объяснить в ИИ-помощнике</Link>
                <Link href="/analytics">Открыть отчёты</Link>
                <Link href="/support?context=reproduction">Поддержка</Link>
              </div>
              <p className="small-muted" style={{ marginTop: 12 }}>{view.parityNote}</p>
            </Card>
          </div>
          <div className="grid grid-2">
            <div>
              <h2 className="section-title">Алерты воспроизводства</h2>
              <AlertList items={view.alerts} />
            </div>
            <div>
              <h2 className="section-title">Задачи воспроизводства</h2>
              <WorklistList items={view.worklists} />
            </div>
          </div>
          <Card>
            <h3 className="card-title">Планировщик — предпросмотр</h3>
            {view.planPreview.length === 0 ? <p className="small-muted">Недельных планов для текущего контекста нет.</p> : (
              <div className="grid">
                {view.planPreview.map((plan) => (
                  <div className="linked-action-card" key={plan.plan_id}>
                    <div className="linked-action-count">{plan.item_count}</div>
                    <div>
                      <div className="linked-action-title">{plan.name}</div>
                      <div className="linked-action-caption">неделя: {plan.week_start} · ферма: {plan.farm_id || 'все'} · статус: {plan.approved_at ? 'согласован' : 'ожидает'}</div>
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
