'use client';
import Link from 'next/link';
import { useEffect, useState } from 'react';
import { Card, MetricCard } from '@/components/ui/card';
import { DataTable } from '@/components/ui/data-table';
import { ScopeSummary } from '@/components/operations/scope-summary';
import {
  fetchExtendedBundle,
  buildEconomicsViewModel,
  type EconomicsViewModel,
} from '@/lib/api/extended-surfaces';
import {
  fetchEconomicsSummary,
  type EconomicsSummaryResponse,
} from '@/lib/api/economics-summary';

const DEFAULT_DATA_VERSION = 'dv_demo_farm_v1';

type TabKey = 'operations' | 'strategy' | 'scenarios';

function fmtRub(value: number | null | undefined, fractionDigits = 0): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  return `${value.toLocaleString('ru-RU', {
    minimumFractionDigits: fractionDigits,
    maximumFractionDigits: fractionDigits,
  })} ₽`;
}

function fmtMillions(value: number | null | undefined, fractionDigits = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  if (Math.abs(value) >= 1_000_000) {
    return `${(value / 1_000_000).toLocaleString('ru-RU', {
      minimumFractionDigits: fractionDigits,
      maximumFractionDigits: fractionDigits,
    })} M ₽`;
  }
  return `${value.toLocaleString('ru-RU', {
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  })} ₽`;
}

function fmtPct(value: number | null | undefined, fractionDigits = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  return `${value.toLocaleString('ru-RU', {
    minimumFractionDigits: fractionDigits,
    maximumFractionDigits: fractionDigits,
  })} %`;
}

function fmtRatio(value: number | null | undefined, fractionDigits = 2): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  return `${value.toLocaleString('ru-RU', {
    minimumFractionDigits: fractionDigits,
    maximumFractionDigits: fractionDigits,
  })}×`;
}

function fmtPerUnit(
  value: number | null | undefined,
  suffix: string,
  fractionDigits = 1,
): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  return `${value.toLocaleString('ru-RU', {
    minimumFractionDigits: fractionDigits,
    maximumFractionDigits: fractionDigits,
  })} ${suffix}`;
}

function fmtMonths(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  return `${value.toLocaleString('ru-RU', {
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  })} мес`;
}

interface TabsProps {
  tabs: ReadonlyArray<{ key: TabKey; label: string }>;
  active: TabKey;
  onSelect: (key: TabKey) => void;
}

function Tabs({ tabs, active, onSelect }: TabsProps) {
  return (
    <div className="economics-tabs" role="tablist">
      {tabs.map((t) => (
        <button
          key={t.key}
          role="tab"
          aria-selected={t.key === active}
          className={`economics-tab${t.key === active ? ' is-active' : ''}`}
          onClick={() => onSelect(t.key)}
          type="button"
        >
          {t.label}
        </button>
      ))}
    </div>
  );
}

function OperationsTab({ summary }: { summary: EconomicsSummaryResponse | null }) {
  if (!summary) return <div className="card">Загрузка экономики…</div>;
  const { kpi, revenue, cost, per_cow_day: perCowDay, sensitivity, roi_actions: roi } = summary;
  return (
    <>
      <div className="grid grid-4">
        <MetricCard
          title="Маржа / корова / день"
          value={fmtRub(perCowDay.margin_rub ?? kpi.margin_per_cow_per_day_rub, 0)}
        />
        <MetricCard title="Всего маржи за период" value={fmtMillions(kpi.total_margin_rub)} />
        <MetricCard title="Себестоимость литра" value={fmtPerUnit(kpi.cost_per_liter_rub, '₽/л', 1)} />
        <MetricCard title="Margin %" value={fmtPct(kpi.margin_pct, 1)} />
      </div>

      <div className="grid grid-2">
        <Card>
          <h3 className="card-title">Выручка</h3>
          <div className="kv-list">
            <div><span>Молоко</span><strong>{fmtMillions(revenue.milk_rub)}</strong></div>
            <div><span>Выбраковка</span><strong>{fmtMillions(revenue.cull_rub)}</strong></div>
            <div><span>Итого</span><strong>{fmtMillions(revenue.total_rub)}</strong></div>
          </div>
        </Card>
        <Card>
          <h3 className="card-title">Затраты</h3>
          <div className="kv-list">
            <div><span>Корм</span><strong>{fmtMillions(cost.feed_rub)} ({(cost.breakdown_pct.feed ?? 0).toFixed(0)}%)</strong></div>
            <div><span>Вет.</span><strong>{fmtMillions(cost.vet_rub)} ({(cost.breakdown_pct.vet ?? 0).toFixed(0)}%)</strong></div>
            <div><span>Репро</span><strong>{fmtMillions(cost.repro_rub)} ({(cost.breakdown_pct.repro ?? 0).toFixed(0)}%)</strong></div>
            <div><span>Выбраковка</span><strong>{fmtMillions(cost.cull_rub)} ({(cost.breakdown_pct.cull ?? 0).toFixed(0)}%)</strong></div>
            <div><span>Прочее</span><strong>{fmtMillions(cost.other_rub)} ({(cost.breakdown_pct.other ?? 0).toFixed(0)}%)</strong></div>
            <div><span>Итого</span><strong>{fmtMillions(cost.total_rub)}</strong></div>
          </div>
        </Card>
      </div>

      <Card>
        <h3 className="card-title">Чувствительность (breakeven, single-input)</h3>
        <div className="kv-list">
          <div>
            <span>Цена молока (нижняя граница)</span>
            <strong>{fmtPerUnit(sensitivity.milk_price_floor_rub_per_kg, '₽/кг', 1)}</strong>
          </div>
          <div>
            <span>Стоимость корма (верхняя граница)</span>
            <strong>{fmtPerUnit(sensitivity.feed_cost_ceiling_rub_per_kg_dm, '₽/кг ДВ', 1)}</strong>
          </div>
          <div>
            <span>Стоимость вет.события (верхняя граница)</span>
            <strong>{fmtPerUnit(sensitivity.vet_cost_ceiling_rub_per_event, '₽/событие', 0)}</strong>
          </div>
        </div>
        <p className="small-muted" style={{ marginTop: 8 }}>
          Метод: {sensitivity.method}. Граничные значения, при которых margin = 0 если изменить
          только этот вход, остальные удержаны.
        </p>
      </Card>

      <Card>
        <h3 className="card-title">ROI действий (топ-5 за период)</h3>
        {roi.length === 0 ? (
          <p className="small-muted">Нет данных roi_attribution за период. Запустите ROI-расчёт.</p>
        ) : (
          <DataTable
            rows={roi as unknown as Array<Record<string, unknown>>}
            columns={[
              { key: 'label', header: 'Действие', render: (row) => String(row.label || row.action_id) },
              { key: 'cohort_n', header: 'Когорта', render: (row) => String(row.cohort_n ?? '—') },
              { key: 'delta_margin_per_cow_day_rub', header: 'Δ ₽/корова/день', render: (row) => fmtRub(row.delta_margin_per_cow_day_rub as number | null, 0) },
              { key: 'total_margin_delta_rub', header: 'Δ ₽ за окно', render: (row) => fmtRub(row.total_margin_delta_rub as number | null, 0) },
              { key: 'method', header: 'Метод', render: (row) => String(row.method || '—') },
            ]}
          />
        )}
      </Card>
    </>
  );
}

function StrategyTab({ summary }: { summary: EconomicsSummaryResponse | null }) {
  if (!summary) return <div className="card">Загрузка стратегических показателей…</div>;
  const { strategic_kpi: sk, unit_economics_ladder: ladder, ai_cost: ai } = summary;

  return (
    <>
      <Card>
        <h3 className="card-title">Стратегия (целевые показатели)</h3>
        <p className="small-muted" style={{ marginBottom: 12 }}>
          Все значения — целевые, не валидированы на реальных пилотах. См.{' '}
          <Link href="/copilot?context=economics">investor_faq</Link> q.22 disclaimer.
          Допущения: acquisition_cost_rub_per_cow={fmtRub(sk.acquisition_cost_rub_per_cow, 0)},
          saas_cac_rub={fmtRub(sk.saas_cac_rub, 0)}, lifetime_years={sk.lifetime_years ?? '—'},
          retention_months={sk.retention_months ?? '—'}.
        </p>
        <div className="grid grid-4">
          <MetricCard title="ROI на корову (годовой)" value={fmtPct(sk.roi_per_cow_per_year_pct, 1)} />
          <MetricCard title="ROI на корову (lifetime)" value={fmtPct(sk.roi_per_cow_lifetime_pct, 1)} />
          <MetricCard title="Payback" value={fmtMonths(sk.payback_months)} />
          <MetricCard title="LTV / CAC" value={fmtRatio(sk.ltv_cac_ratio, 2)} />
        </div>
      </Card>

      <Card>
        <h3 className="card-title">Unit economics ladder</h3>
        <div className="grid grid-3">
          <MetricCard title="Топ 25% (маржа/корова/день)" value={fmtRub(ladder.top_quartile_margin_rub, 0)} />
          <MetricCard title="Медиана" value={fmtRub(ladder.median_margin_rub, 0)} />
          <MetricCard title="Нижние 10%" value={fmtRub(ladder.bottom_decile_margin_rub, 0)} />
        </div>
        {ladder.bottom_decile_cohort_n !== null && ladder.bottom_decile_cohort_n > 0 ? (
          <p className="small-muted" style={{ marginTop: 12 }}>
            В нижнем дециле {ladder.bottom_decile_cohort_n} коров. {ladder.bottom_decile_cohort_ref ? (
              <Link href={`/worklists?context=${encodeURIComponent(ladder.bottom_decile_cohort_ref)}`}>
                Открыть culling review
              </Link>
            ) : null}
          </p>
        ) : (
          <p className="small-muted" style={{ marginTop: 12 }}>
            Нет данных unit_economics за период. Запустите расчёт.
          </p>
        )}
      </Card>

      {ai ? (
        <Card>
          <h3 className="card-title">AI cost (прозрачность)</h3>
          <div className="kv-list">
            <div><span>За период</span><strong>{fmtRub(ai.period_rub, 0)}</strong></div>
            <div><span>На корову в год</span><strong>{fmtRub(ai.per_cow_per_year_rub, 1)}</strong></div>
          </div>
        </Card>
      ) : null}
    </>
  );
}

function firstScenarioDataVersion(scenarios: Array<Record<string, unknown>>): string | null {
  for (const item of scenarios) {
    const value = typeof item.data_version === 'string' ? item.data_version.trim() : '';
    if (value) return value;
  }
  return null;
}

function ScenariosTab({ view }: { view: EconomicsViewModel | null }) {
  if (!view) return <div className="card">Загрузка сценариев…</div>;
  const dataVersion =
    firstScenarioDataVersion(view.scenarios as unknown as Array<Record<string, unknown>>) ||
    DEFAULT_DATA_VERSION;
  const assistantHref = `/copilot?data_version=${encodeURIComponent(dataVersion)}&section=modules.economics`;

  return (
    <>
      <div className="grid grid-3">
        <MetricCard title="Сценарии" value={view.summary.scenariosTotal} />
        <MetricCard title="Отчёты" value={view.summary.reportsTotal} />
        <MetricCard
          title="Decision acceptance"
          value={`${Math.round(view.summary.decisionAcceptanceRate * 100)}%`}
        />
      </div>

      <div className="grid grid-2">
        <ScopeSummary scope={view.scope} />
        <Card>
          <h3 className="card-title">Linked office flows</h3>
          <div className="linked-inline-actions">
            <Link href="/analytics">Open reports</Link>
            <Link href={assistantHref}>Explain in assistant</Link>
            <Link href="/decisions?context=economics">Decision trail</Link>
            <Link href="/support?context=economics">Support / pilot evidence</Link>
          </div>
        </Card>
      </div>

      <DataTable
        rows={view.scenarios}
        columns={[
          { key: 'name', header: 'Сценарий', render: (row) => row.name || row.scenario_id },
          { key: 'status', header: 'Статус', render: (row) => row.status },
          { key: 'report_version', header: 'Версия отчёта', render: (row) => row.report_version || '—' },
          { key: 'data_version', header: 'data_version', render: (row) => row.data_version || '—' },
        ]}
      />
    </>
  );
}

export function EconomicsMasterSurface() {
  const [tab, setTab] = useState<TabKey>('operations');
  const [view, setView] = useState<EconomicsViewModel | null>(null);
  const [summary, setSummary] = useState<EconomicsSummaryResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    void fetchExtendedBundle()
      .then((bundle) => {
        if (active) setView(buildEconomicsViewModel(bundle));
      })
      .catch((err) => {
        if (active) setError(err instanceof Error ? err.message : 'Не удалось загрузить сценарии');
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (tab === 'scenarios') return;
    let active = true;
    void fetchEconomicsSummary({ data_version: DEFAULT_DATA_VERSION })
      .then((data) => {
        if (active) setSummary(data);
      })
      .catch((err) => {
        if (active) setError(err instanceof Error ? err.message : 'Не удалось загрузить сводку');
      });
    return () => {
      active = false;
    };
  }, [tab]);

  return (
    <div className="grid">
      <h1 className="page-title">Экономика</h1>
      <p className="page-subtitle">
        Маржа фермы, чувствительность и ROI. Цифры на табе «Стратегия» — целевые до подтверждения пилотами.
      </p>
      <Tabs
        tabs={[
          { key: 'operations', label: 'Оперативно' },
          { key: 'strategy', label: 'Стратегия' },
          { key: 'scenarios', label: 'Сценарии' },
        ]}
        active={tab}
        onSelect={setTab}
      />
      {error ? <div className="card error-text">{error}</div> : null}
      {tab === 'operations' ? <OperationsTab summary={summary} /> : null}
      {tab === 'strategy' ? <StrategyTab summary={summary} /> : null}
      {tab === 'scenarios' ? <ScenariosTab view={view} /> : null}
      {summary && summary.warnings.length > 0 ? (
        <details className="card" style={{ marginTop: 16 }}>
          <summary>Предупреждения backend ({summary.warnings.length})</summary>
          <ul style={{ margin: '8px 0 0 0', paddingLeft: 16 }}>
            {summary.warnings.map((w, i) => (
              <li key={i} className="small-muted">{w}</li>
            ))}
          </ul>
        </details>
      ) : null}
    </div>
  );
}
