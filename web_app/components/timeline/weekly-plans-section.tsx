'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { Card, MetricCard } from '@/components/ui/card';
import { apiFetch } from '@/lib/api/client';
import type { PlannerResponse } from '@/lib/api/contracts';

export function WeeklyPlansSection() {
  const [data, setData] = useState<PlannerResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    apiFetch<PlannerResponse>('/planner')
      .then((d) => { if (active) setData(d); })
      .catch((e) => { if (active) setError(e instanceof Error ? e.message : String(e)); });
    return () => { active = false; };
  }, []);

  if (error) {
    return (
      <Card>
        <h3 className="card-title">Недельные планы</h3>
        <p className="error-text">Не удалось загрузить: {error}</p>
      </Card>
    );
  }
  if (!data) return null;

  return (
    <Card>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
        <h3 className="card-title">Недельные планы</h3>
        <Link href="/worklists" className="small-muted">К рабочим спискам →</Link>
      </div>
      <div className="grid grid-3" style={{ marginBottom: 12 }}>
        <MetricCard title="Открытых задач" value={data.summary.tasks_open} />
        <MetricCard title="Просроченных" value={data.summary.overdue_active} />
        <MetricCard title="Ожидают подтверждения" value={data.pending_approvals} />
      </div>
      {data.weekly_plans.length > 0 ? (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Название</th>
                <th>Статус</th>
                <th>Начало недели</th>
                <th>Задач</th>
                <th>Ферма</th>
              </tr>
            </thead>
            <tbody>
              {data.weekly_plans.map((plan) => (
                <tr key={plan.plan_id}>
                  <td>{plan.name}</td>
                  <td>{plan.status}</td>
                  <td>{plan.week_start}</td>
                  <td>{plan.item_count}</td>
                  <td>{plan.farm_id ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="small-muted">Нет недельных планов на текущий период.</p>
      )}
    </Card>
  );
}
