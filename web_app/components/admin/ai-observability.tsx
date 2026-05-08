'use client';
import { useEffect, useState } from 'react';
import { Card, MetricCard } from '@/components/ui/card';
import { DataTable } from '@/components/ui/data-table';
import {
  fetchAiStats,
  fetchAiCalls,
  fetchGroundingRate,
  triggerMorningBrief,
  triggerInsightsScan,
  type AiStats,
  type AiCallRow,
  type GroundingRate,
} from '@/lib/api/admin-ai';
import { AiCallTraceDrawer } from './ai-call-trace-drawer';

type Period = 1 | 24 | 168;
const PERIOD_LABEL: Record<Period, string> = { 1: '1 ч', 24: '24 ч', 168: '7 дн' };

export function AiObservability() {
  const [period, setPeriod] = useState<Period>(24);
  const [stats, setStats] = useState<AiStats | null>(null);
  const [grounding, setGrounding] = useState<GroundingRate | null>(null);
  const [calls, setCalls] = useState<AiCallRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [openCallId, setOpenCallId] = useState<number | null>(null);
  const [triggerBusy, setTriggerBusy] = useState<'morning' | 'scan' | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let active = true;
    setError(null);
    Promise.all([fetchAiStats(period), fetchGroundingRate(period), fetchAiCalls({ limit: 100 })])
      .then(([s, g, c]) => {
        if (!active) return;
        setStats(s);
        setGrounding(g);
        setCalls(c);
      })
      .catch((e) => {
        if (!active) return;
        setError(e instanceof Error && e.message === 'forbidden' ? 'Нет прав доступа' : String(e));
      });
    return () => {
      active = false;
    };
  }, [period, reloadKey]);

  async function handleTrigger(name: 'morning' | 'scan') {
    setTriggerBusy(name);
    try {
      if (name === 'morning') await triggerMorningBrief();
      else await triggerInsightsScan();
      setReloadKey((k) => k + 1);
    } catch (e) {
      setError(`Триггер ${name} провалился: ${e}`);
    } finally {
      setTriggerBusy(null);
    }
  }

  if (error === 'Нет прав доступа') {
    return <div className="card error-text">Нет прав доступа</div>;
  }

  return (
    <div className="grid">
      <div className="topbar">
        <div>
          <h1 className="page-title">AI-наблюдаемость</h1>
          <p className="page-subtitle">Сводка вызовов LLM, grounding rate и trace отдельных вызовов.</p>
        </div>
        <div className="period-tabs">
          {([1, 24, 168] as Period[]).map((p) => (
            <button
              key={p}
              className={p === period ? 'period-tab active' : 'period-tab'}
              onClick={() => setPeriod(p)}
            >
              {PERIOD_LABEL[p]}
            </button>
          ))}
        </div>
      </div>

      {error && <div className="card error-text">{error}</div>}

      <div className="grid grid-4">
        <MetricCard title={`Вызовов за ${PERIOD_LABEL[period]}`} value={stats ? stats.count : '—'} />
        <MetricCard title="p95 латентность" value={stats ? `${(stats.p95_latency_ms / 1000).toFixed(1)} с` : '—'} />
        <MetricCard title="Токенов всего" value={stats ? stats.total_tokens.toLocaleString('ru-RU') : '—'} />
        <MetricCard title="Стоимость" value={stats ? `$${stats.total_cost_usd.toFixed(2)}` : '—'} />
      </div>

      <div className="grid grid-2">
        <Card>
          <h3 className="card-title">Grounding rate</h3>
          {grounding ? (
            <>
              <div className="big-number">{grounding.rate_pct.toFixed(1)}%</div>
              <p className="small-muted">
                {grounding.with_evidence} из {grounding.total} с evidence
              </p>
            </>
          ) : (
            <p className="muted">—</p>
          )}
        </Card>

        <Card>
          <h3 className="card-title">Ручные триггеры</h3>
          <div className="action-row">
            <button
              data-testid="trigger-morning-brief"
              disabled={triggerBusy !== null}
              onClick={() => handleTrigger('morning')}
            >
              {triggerBusy === 'morning' ? 'Генерация…' : 'Сгенерировать утренний брифинг'}
            </button>
            <button
              data-testid="trigger-insights-scan"
              disabled={triggerBusy !== null}
              onClick={() => handleTrigger('scan')}
            >
              {triggerBusy === 'scan' ? 'Сканирование…' : 'Сканировать инсайты сейчас'}
            </button>
          </div>
        </Card>
      </div>

      <Card>
        <h3 className="card-title">Последние 100 вызовов</h3>
        <DataTable<AiCallRow>
          rows={calls}
          columns={[
            { key: 'id', header: 'ID', render: (r) => String(r.id) },
            { key: 'created_at', header: 'Время', render: (r) => new Date(r.created_at).toLocaleString('ru-RU') },
            { key: 'endpoint', header: 'Endpoint', render: (r) => r.endpoint },
            { key: 'model', header: 'Модель', render: (r) => r.model.replace('claude-', '') },
            { key: 'latency_ms', header: 'Latency', render: (r) => `${(r.latency_ms / 1000).toFixed(1)} с` },
            { key: 'total_tokens', header: 'Токенов', render: (r) => String(r.total_tokens) },
            { key: 'cost_usd', header: 'Стоимость', render: (r) => `$${r.cost_usd.toFixed(4)}` },
            { key: 'has_error', header: 'Статус', render: (r) => (r.has_error ? '✗' : '✓') },
          ]}
          onRowClick={(row) => setOpenCallId(row.id)}
        />
      </Card>

      <AiCallTraceDrawer callId={openCallId} onClose={() => setOpenCallId(null)} />
    </div>
  );
}
