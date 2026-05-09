'use client';

import { useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import { Card, MetricCard } from '@/components/ui/card';
import { FilterBar } from '@/components/ui/filter-bar';
import { DataTable, type TableColumn } from '@/components/ui/data-table';
import { EmptyState } from '@/components/ui/empty-state';
import { ExplainabilityBlock } from '@/components/ui/explainability-block';
import { apiFetch } from '@/lib/api/client';
import { normalizeListResponse, type ListResponse } from '@/lib/api/contracts';

type DecisionRow = {
  decision_id?: string;
  action?: string;
  username?: string;
  user_id?: string;
  created_at?: string;
  reason_code?: string;
  recommendation_id?: string;
  decision_type?: string;
  metadata_json?: string;
};

export default function DecisionsPage() {
  const searchParams = useSearchParams();

  const params = useMemo(() => {
    const out: Record<string, string> = {};
    for (const [key, value] of searchParams.entries()) out[key] = value;
    return out;
  }, [searchParams]);

  const [rows, setRows] = useState<DecisionRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState('');

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    void apiFetch<ListResponse<DecisionRow>>('/decisions')
      .then((data) => { if (active) setRows(normalizeListResponse(data).items); })
      .catch((err) => {
        if (active) {
          setError(err instanceof Error ? err.message : 'Ошибка загрузки данных');
          setRows([]);
        }
      })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);

  const filtered = useMemo(
    () => (!query ? rows : rows.filter((row) => JSON.stringify(row).toLowerCase().includes(query.toLowerCase()))),
    [rows, query],
  );

  const metrics = useMemo(() => {
    const total = rows.length;
    const byAction = rows.reduce<Record<string, number>>((acc, r) => {
      const k = String(r.action || 'unknown');
      acc[k] = (acc[k] || 0) + 1;
      return acc;
    }, {});
    const cullCount = byAction['cull_recommended'] ?? 0;
    const lastDay = rows.filter((r) => {
      if (!r.created_at) return false;
      const t = Date.parse(String(r.created_at));
      return !Number.isNaN(t) && Date.now() - t < 24 * 3600 * 1000;
    }).length;
    return { total, cullCount, lastDay, byAction };
  }, [rows]);

  const columns: TableColumn<DecisionRow>[] = useMemo(() => [
    { key: 'decision_id', header: 'ID', render: (row) => String(row.decision_id ?? '—') },
    { key: 'action', header: 'Действие', render: (row) => String(row.action ?? '—') },
    { key: 'decision_type', header: 'Тип', render: (row) => String(row.decision_type ?? '—') },
    { key: 'username', header: 'Автор', render: (row) => String(row.username ?? row.user_id ?? '—') },
    { key: 'reason_code', header: 'Reason', render: (row) => String(row.reason_code ?? '—') },
    { key: 'created_at', header: 'Создано', render: (row) => String(row.created_at ?? '—') },
  ], []);

  return (
    <div className="grid">
      <div className="topbar">
        <div>
          <h1 className="page-title">Решения</h1>
          <p className="page-subtitle">
            Журнал решений по животным (keep / cull / treat / defer) с привязкой
            к рекомендациям, аудит-трейлом и автором.
          </p>
        </div>
      </div>

      <div className="grid grid-3">
        <MetricCard title="Всего решений" value={metrics.total} />
        <MetricCard title="Выбраковка (cull)" value={metrics.cullCount} />
        <MetricCard title="За последние 24 ч" value={metrics.lastDay} />
      </div>

      {Object.keys(params).length > 0 && (
        <Card>
          <h3 className="card-title">Контекст принятого решения</h3>
          <pre style={{ whiteSpace: 'pre-wrap', margin: 0, fontSize: 12 }}>
            {JSON.stringify(params, null, 2)}
          </pre>
        </Card>
      )}

      <ExplainabilityBlock
        title="Принципы работы"
        reasons={[
          'Семантика журнала решений неизменна и полностью аудируема (CLAUDE.md §5).',
          'Веб-оболочка читает канонический контрактный слой, общий с Android.',
          'Каждое решение привязано к recommendation_id (NPV, инсайт, алерт) для feedback-loop калибровки моделей.',
        ]}
      />

      <Card>
        <h3 className="card-title">Журнал решений</h3>
        <FilterBar placeholder="Поиск по решениям…" onChange={setQuery} />
        {loading && <div style={{ marginTop: 12 }}>Загрузка…</div>}
        {!loading && error && <div className="error-text" style={{ marginTop: 12 }}>{error}</div>}
        {!loading && !error && filtered.length === 0 && (
          <EmptyState
            title="Записей пока нет"
            description="Данные загружаются с бэкенда через канонический API."
          />
        )}
        {!loading && !error && filtered.length > 0 && (
          <div style={{ marginTop: 12 }}>
            <DataTable rows={filtered} columns={columns} />
          </div>
        )}
      </Card>
    </div>
  );
}
