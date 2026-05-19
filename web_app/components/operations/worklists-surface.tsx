'use client';
import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { MetricCard, Card } from '@/components/ui/card';
import { FilterBar } from '@/components/ui/filter-bar';
import { WorklistList } from '@/components/ui/worklist-list';
import { apiFetch } from '@/lib/api/client';
import type { WorklistItem, ListResponse, PersonnelListResponse } from '@/lib/api/contracts';
import { normalizeListResponse } from '@/lib/api/contracts';
import { pathLabels } from '@/lib/navigation';
import { useDomainLabels } from '@/lib/hooks/use-domain-labels';

export function WorklistsSurface() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const domain = searchParams.get('domain');
  const { label: domainLabel } = useDomainLabels();

  const [data, setData] = useState<ListResponse<WorklistItem> | null>(null);
  const [query, setQuery] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [personnelUserIds, setPersonnelUserIds] = useState<Set<number> | null>(null);
  const [hideOrphans, setHideOrphans] = useState(false);

  useEffect(() => {
    let active = true;
    setData(null);
    setError(null);
    const qs = new URLSearchParams();
    if (domain) qs.set('domain', domain);
    const path = qs.toString() ? `/worklists?${qs.toString()}` : '/worklists';
    void apiFetch<ListResponse<WorklistItem>>(path)
      .then((res) => { if (active) setData(normalizeListResponse(res)); })
      .catch((err) => { if (active) setError(err instanceof Error ? err.message : 'Ошибка загрузки задач'); });
    return () => { active = false; };
  }, [domain]);

  useEffect(() => {
    let active = true;
    void apiFetch<PersonnelListResponse>('/personnel?has_user=true&limit=500')
      .then((res) => {
        if (!active) return;
        const ids = new Set<number>();
        for (const p of res.items ?? []) {
          if (typeof p.user_id === 'number') ids.add(p.user_id);
        }
        setPersonnelUserIds(ids);
      })
      .catch(() => {
        if (active) setPersonnelUserIds(new Set());
      });
    return () => { active = false; };
  }, []);

  const items = useMemo(() => {
    let rows = data?.items || [];
    if (hideOrphans && personnelUserIds) {
      rows = rows.filter((item) => {
        if (item.owner_user_id == null) return true;
        return personnelUserIds.has(item.owner_user_id);
      });
    }
    if (!query) return rows;
    return rows.filter((item) => JSON.stringify(item).toLowerCase().includes(query.toLowerCase()));
  }, [data, query, hideOrphans, personnelUserIds]);

  const orphanCount = useMemo(() => {
    if (!personnelUserIds || !data) return 0;
    return (data.items || []).filter(
      (item) => item.owner_user_id != null && !personnelUserIds.has(item.owner_user_id),
    ).length;
  }, [data, personnelUserIds]);

  const open = items.filter((item) => item.status !== 'done' && item.status !== 'cancelled').length;
  const overdue = items.filter((item) => item.is_overdue && item.status !== 'done' && item.status !== 'cancelled').length;

  const resetDomain = () => {
    const next = new URLSearchParams(searchParams.toString());
    next.delete('domain');
    const qs = next.toString();
    router.replace(qs ? `/worklists?${qs}` : '/worklists', { scroll: false });
  };

  return (
    <div className="grid">
      <h1 className="page-title">{pathLabels['/worklists']}</h1>
      <p className="page-subtitle">Ежедневные очереди задач с привязкой к действиям и объяснениям.</p>
      {domain ? (
        <div className="card" role="status" aria-live="polite" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12 }}>
          <span>Фильтр: домейн = <strong>{domainLabel(domain)}</strong> ({domain})</span>
          <button type="button" className="btn btn-secondary" onClick={resetDomain}>Сбросить</button>
        </div>
      ) : null}
      <FilterBar placeholder="Фильтр по ферме, задаче, исполнителю или алерту…" onChange={setQuery} />
      {orphanCount > 0 ? (
        <div
          className="card"
          role="group"
          aria-label="Orphan tasks filter"
          style={{ display: 'flex', alignItems: 'center', gap: 12 }}
        >
          <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
            <input
              type="checkbox"
              checked={hideOrphans}
              onChange={(e) => setHideOrphans(e.target.checked)}
            />
            <span>Скрыть задачи удалённых сотрудников</span>
          </label>
          <span style={{ fontSize: 12, color: 'var(--text-muted, #667085)' }}>
            ({orphanCount} {orphanCount === 1 ? 'задача' : 'задач'} с owner без personnel-карточки)
          </span>
        </div>
      ) : null}
      <div className="grid grid-3">
        <MetricCard title="Всего задач" value={items.length} />
        <MetricCard title="Открытых задач" value={open} />
        <MetricCard title="Просроченных" value={overdue} />
      </div>
      {error ? <div className="card error-text">{error}</div> : null}
      {!data ? <div className="card">Загружаю задачи…</div> : null}
      {data ? (
        <>
          <WorklistList items={items.slice(0, 10)} />
          <Card>
            <h3 className="card-title">Связанные действия</h3>
            <div className="linked-inline-actions">
              <Link href="/timeline">Открыть планировщик</Link>
              <Link href="/decisions">Журнал решений</Link>
              <Link href="/support">Обратная связь / поддержка</Link>
            </div>
          </Card>
        </>
      ) : null}
    </div>
  );
}
