'use client';

import { useEffect, useState } from 'react';
import { Card } from '@/components/ui/card';
import { EmptyState } from '@/components/ui/empty-state';
import { DataTable, type TableColumn } from '@/components/ui/data-table';
import type { FeedingRation, FeedIntakeDrop } from '@/lib/api/contracts';
import { getFeedingRations, getFeedIntakeDrops } from '@/lib/api/feeding';

const rationColumns: TableColumn<FeedingRation>[] = [
  { key: 'group_name', header: 'Группа', render: (r) => r.group_name },
  { key: 'ration_name', header: 'Рацион', render: (r) => r.ration_name },
  { key: 'dm_kg', header: 'СВ, кг', render: (r) => (r.dm_kg !== null && r.dm_kg !== undefined ? r.dm_kg.toFixed(1) : '—') },
  { key: 'last_distribution_at', header: 'Последняя раздача', render: (r) => r.last_distribution_at ?? '—' },
  { key: 'status', header: 'Статус', render: (r) => r.status },
];

function formatPct(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—';
  return `${value.toFixed(1)}%`;
}

export default function FeedingPage() {
  const [rations, setRations] = useState<FeedingRation[] | null>(null);
  const [drops, setDrops] = useState<FeedIntakeDrop[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    Promise.all([getFeedingRations(), getFeedIntakeDrops()])
      .then(([rationsResp, dropsResp]) => {
        if (!alive) return;
        setRations(rationsResp.items);
        setDrops(dropsResp.items);
      })
      .catch((e: unknown) => {
        if (!alive) return;
        setError(e instanceof Error ? e.message : String(e));
      });
    return () => {
      alive = false;
    };
  }, []);

  return (
    <div className="page">
      <header className="page-head">
        <h1>Кормление</h1>
        <nav aria-label="Хлебные крошки" className="breadcrumbs">
          <span>Стадо</span>
          <span aria-hidden> › </span>
          <span aria-current="page">Кормление</span>
        </nav>
      </header>

      {error && (
        <Card>
          <div role="alert" className="card-title">Ошибка загрузки</div>
          <p className="card-subtitle">{error}</p>
        </Card>
      )}

      <section>
        <h2 className="section-title">Рационы по группам</h2>
        {rations === null && !error ? (
          <Card><p className="card-subtitle">Загрузка…</p></Card>
        ) : rations && rations.length > 0 ? (
          <DataTable rows={rations} columns={rationColumns} />
        ) : (
          <EmptyState title="Рационы ещё не настроены" description="Заполните configs/feeding/rations_v1.yaml на стороне фермы." />
        )}
      </section>

      <section>
        <h2 className="section-title">Группы со снижением потребления</h2>
        {drops === null && !error ? (
          <Card><p className="card-subtitle">Загрузка…</p></Card>
        ) : drops && drops.length > 0 ? (
          <div className="card-grid">
            {drops.map((d) => (
              <Card key={d.insight_id}>
                <h3 className="card-title">{d.group_name ?? d.title}</h3>
                <dl className="card-dl">
                  <div><dt>Падение</dt><dd>{formatPct(d.drop_pct)}</dd></div>
                  <div><dt>Окно</dt><dd>{d.window_days ? `${d.window_days} д.` : '—'}</dd></div>
                  <div><dt>Зафиксировано</dt><dd>{d.last_observed_at ?? '—'}</dd></div>
                </dl>
              </Card>
            ))}
          </div>
        ) : (
          <EmptyState title="Снижения потребления не выявлены" description="При появлении инсайтов с типом feed_intake_drop / dmi_drop они появятся здесь." />
        )}
      </section>
    </div>
  );
}
