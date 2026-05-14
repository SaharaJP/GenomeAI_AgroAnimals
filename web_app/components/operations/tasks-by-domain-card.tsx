'use client';

import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { Card } from '@/components/ui/card';
import { apiFetch } from '@/lib/api/client';
import { normalizeListResponse, type ListResponse, type WorklistItem } from '@/lib/api/contracts';
import { useDomainLabels } from '@/lib/hooks/use-domain-labels';

type Props = {
  domain: string;
  title?: string;
  limit?: number;
};

function isDueToday(dueAt: string | null | undefined): boolean {
  if (!dueAt) return false;
  const d = new Date(dueAt);
  if (Number.isNaN(d.getTime())) return false;
  const now = new Date();
  return d.getUTCFullYear() === now.getUTCFullYear()
    && d.getUTCMonth() === now.getUTCMonth()
    && d.getUTCDate() === now.getUTCDate();
}

function isActive(status: string): boolean {
  return status !== 'done' && status !== 'cancelled';
}

function formatDue(dueAt: string | null | undefined): string {
  if (!dueAt) return 'без срока';
  const d = new Date(dueAt);
  if (Number.isNaN(d.getTime())) return dueAt;
  return d.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
}

export function TasksByDomainCard({ domain, title = 'Задачи по направлению', limit = 5 }: Props) {
  const { label } = useDomainLabels();
  const [items, setItems] = useState<WorklistItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setItems(null);
    setError(null);
    const qs = new URLSearchParams({ domain, limit: String(Math.max(limit, 5)) });
    void apiFetch<ListResponse<WorklistItem>>(`/worklists?${qs.toString()}`)
      .then((res) => {
        if (!active) return;
        setItems(normalizeListResponse(res).items);
      })
      .catch((err) => {
        if (active) setError(err instanceof Error ? err.message : 'Ошибка загрузки задач');
      });
    return () => { active = false; };
  }, [domain, limit]);

  const counters = useMemo(() => {
    const rows = items ?? [];
    const open = rows.filter((r) => isActive(r.status)).length;
    const overdue = rows.filter((r) => r.is_overdue && isActive(r.status)).length;
    const today = rows.filter((r) => isActive(r.status) && isDueToday(r.due_at)).length;
    return { open, overdue, today };
  }, [items]);

  const top = useMemo(() => {
    const rows = (items ?? []).filter((r) => isActive(r.status));
    rows.sort((a, b) => (a.due_at ?? '~').localeCompare(b.due_at ?? '~'));
    return rows.slice(0, limit);
  }, [items, limit]);

  return (
    <Card>
      <h3 className="card-title">{title}</h3>
      <p className="card-subtitle">Домен: {label(domain)}</p>
      {error ? <div className="error-text" style={{ marginTop: 8 }}>{error}</div> : null}
      {items === null && !error ? <div style={{ marginTop: 8 }}>Загружаю…</div> : null}
      {items !== null && !error ? (
        <>
          <div style={{ display: 'flex', gap: 16, margin: '8px 0 12px', fontSize: 13, color: 'var(--text-secondary)' }}>
            <span>Открытых <strong style={{ color: 'var(--text)' }}>{counters.open}</strong></span>
            <span>·</span>
            <span>Просрочено SLA <strong style={{ color: 'var(--text)' }}>{counters.overdue}</strong></span>
            <span>·</span>
            <span>На сегодня <strong style={{ color: 'var(--text)' }}>{counters.today}</strong></span>
          </div>
          {top.length === 0 ? (
            <p style={{ margin: '8px 0 12px', color: 'var(--text-secondary)', fontSize: 13 }}>
              Открытых задач по этому направлению нет.
            </p>
          ) : (
            <ul style={{ listStyle: 'none', padding: 0, margin: '0 0 12px', display: 'flex', flexDirection: 'column', gap: 6 }}>
              {top.map((row) => (
                <li
                  key={row.task_id}
                  style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 12, fontSize: 13 }}
                >
                  <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{row.title || row.task_type}</span>
                  <span style={{ color: row.is_overdue ? 'var(--danger, #c0392b)' : 'var(--text-secondary)', whiteSpace: 'nowrap' }}>
                    {row.status === 'open' ? '· к работе' : `· ${row.status}`} · {formatDue(row.due_at)}
                  </span>
                </li>
              ))}
            </ul>
          )}
          <Link href={`/worklists?domain=${encodeURIComponent(domain)}`} className="card-link">
            Открыть все в Задачах →
          </Link>
        </>
      ) : null}
    </Card>
  );
}
