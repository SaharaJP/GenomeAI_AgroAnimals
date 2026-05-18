'use client';

import { useEffect, useMemo, useState, type ChangeEvent, type FormEvent } from 'react';
import { useSearchParams } from 'next/navigation';
import { Card } from '@/components/ui/card';
import { EmptyState } from '@/components/ui/empty-state';
import { ExplainabilityBlock } from '@/components/ui/explainability-block';
import { listAudit, type AuditRow } from '@/lib/api/audit';
import { pathLabels } from '@/lib/navigation';

const DEFAULT_LIMIT = 200;

export default function AdminLogsPage() {
  const params = useSearchParams();
  const initialSource = params?.get('source') ?? '';
  const initialAction = params?.get('action_prefix') ?? '';

  const [source, setSource] = useState(initialSource);
  const [actionPrefix, setActionPrefix] = useState(initialAction);
  const [freeText, setFreeText] = useState('');
  const [rows, setRows] = useState<AuditRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [fetchedAt, setFetchedAt] = useState<Date | null>(null);

  const load = async (): Promise<void> => {
    setLoading(true);
    setError(null);
    try {
      const resp = await listAudit({
        object_id: source.trim() || undefined,
        action_prefix: actionPrefix.trim() || undefined,
        q: freeText.trim() || undefined,
        limit: DEFAULT_LIMIT,
      });
      setRows(resp.rows);
      setFetchedAt(new Date());
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось загрузить логи');
      setRows([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
    // initial fetch on mount + when deep-link params change
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const filteredCount = useMemo(() => (rows ? rows.length : 0), [rows]);

  return (
    <div className="grid">
      <div className="topbar">
        <div>
          <h1 className="page-title">{pathLabels['/admin/logs'] || 'Логи системы'}</h1>
          <p className="page-subtitle">
            Просмотр audit-событий из таблицы `audit_log`. Deep-link с
            `/admin/integrations` ставит фильтр по `object_id`. Только admin
            (permission `audit.view`).
          </p>
        </div>
      </div>

      <Card>
        <h3 className="card-title">Фильтры</h3>
        <form
          onSubmit={(e: FormEvent) => {
            e.preventDefault();
            void load();
          }}
          style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr) auto', gap: 8, alignItems: 'end', marginTop: 8 }}
        >
          <label>
            <span style={{ display: 'block', fontSize: 13, color: 'var(--text-muted, #667085)' }}>object_id (источник)</span>
            <input
              type="text"
              value={source}
              onChange={(e: ChangeEvent<HTMLInputElement>) => setSource(e.target.value)}
              placeholder="llm.openai, batch.selex…"
              style={{ width: '100%', padding: '6px 10px', border: '1px solid var(--border, #d0d5dd)', borderRadius: 6 }}
            />
          </label>
          <label>
            <span style={{ display: 'block', fontSize: 13, color: 'var(--text-muted, #667085)' }}>action_prefix</span>
            <input
              type="text"
              value={actionPrefix}
              onChange={(e: ChangeEvent<HTMLInputElement>) => setActionPrefix(e.target.value)}
              placeholder="integration., iam., briefing…"
              style={{ width: '100%', padding: '6px 10px', border: '1px solid var(--border, #d0d5dd)', borderRadius: 6 }}
            />
          </label>
          <label>
            <span style={{ display: 'block', fontSize: 13, color: 'var(--text-muted, #667085)' }}>свободный текст (q)</span>
            <input
              type="text"
              value={freeText}
              onChange={(e: ChangeEvent<HTMLInputElement>) => setFreeText(e.target.value)}
              placeholder="username / object / error…"
              style={{ width: '100%', padding: '6px 10px', border: '1px solid var(--border, #d0d5dd)', borderRadius: 6 }}
            />
          </label>
          <button
            type="submit"
            disabled={loading}
            style={{
              padding: '8px 16px',
              border: '1px solid var(--border, #d0d5dd)',
              borderRadius: 6,
              background: loading ? 'var(--surface-muted, #f5f5f5)' : 'var(--surface-accent, #eef4ff)',
              cursor: loading ? 'wait' : 'pointer',
            }}
          >
            {loading ? 'Загружаю…' : 'Применить'}
          </button>
        </form>
        {fetchedAt ? (
          <p className="card-subtitle" style={{ marginTop: 10 }}>
            Найдено строк: {filteredCount} · обновлено {fetchedAt.toLocaleTimeString('ru-RU')}
          </p>
        ) : null}
      </Card>

      {error ? (
        <Card>
          <p className="error-text">{error}</p>
        </Card>
      ) : null}

      <Card>
        <h3 className="card-title">События</h3>
        {rows === null ? (
          <p className="card-subtitle">Загрузка…</p>
        ) : rows.length === 0 ? (
          <EmptyState
            title="Нет событий"
            description={source ? `Для object_id=${source} нет записей в audit_log с активной retention-областью.` : 'Уточните фильтры.'}
          />
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
              <thead>
                <tr style={{ borderBottom: '1px solid var(--border, #e4e7ec)', textAlign: 'left' }}>
                  <th style={{ padding: '6px 8px' }}>ts</th>
                  <th style={{ padding: '6px 8px' }}>action</th>
                  <th style={{ padding: '6px 8px' }}>username</th>
                  <th style={{ padding: '6px 8px' }}>object_type</th>
                  <th style={{ padding: '6px 8px' }}>object_id</th>
                  <th style={{ padding: '6px 8px' }}>status</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.id} style={{ borderBottom: '1px solid var(--border, #f2f4f7)' }}>
                    <td style={{ padding: '6px 8px', whiteSpace: 'nowrap' }}>
                      <code>{r.ts}</code>
                    </td>
                    <td style={{ padding: '6px 8px' }}>
                      <code>{r.action}</code>
                    </td>
                    <td style={{ padding: '6px 8px' }}>{r.username ?? '—'}</td>
                    <td style={{ padding: '6px 8px' }}>{r.object_type ?? '—'}</td>
                    <td style={{ padding: '6px 8px' }}>
                      <code>{r.object_id ?? '—'}</code>
                    </td>
                    <td style={{ padding: '6px 8px' }}>{r.status ?? 'ok'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <ExplainabilityBlock
        title="Контракт страницы"
        reasons={[
          'Источник: таблица audit_log (CLAUDE.md §3 «любое привилегированное — audit-logged»).',
          'object_id — стабильный ключ ресурса; для интеграций совпадает с id в /admin/integrations (llm.openai, batch.*).',
          'Retention — active scope; архивные строки доступны через query-параметр scope=archived на /api/audit.',
          'Deep-link: /admin/logs?source=<id> ставит фильтр object_id; ?action_prefix=integration. сужает до интеграционных событий.',
        ]}
      />
    </div>
  );
}
