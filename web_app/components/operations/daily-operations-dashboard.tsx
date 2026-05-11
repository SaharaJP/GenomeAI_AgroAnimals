'use client';

import Link from 'next/link';
import { useEffect, useMemo, useState } from 'react';

import {
  buildDailyOperationsViewModel,
  fetchDailyOperationsBundle,
  type AlertVm,
  type DailyOperationsViewModel,
  type WorklistVm,
} from '@/lib/api/daily-operations';
import { pathLabels } from '@/lib/navigation';

function buttonStyle(): React.CSSProperties {
  return {
    padding: '8px 12px',
    borderRadius: 8,
    border: '1px solid rgba(128,128,128,0.35)',
    background: 'transparent',
    cursor: 'pointer',
  };
}

function MetricCard({ title, value, caption }: { title: string; value: string | number; caption?: string }) {
  return (
    <section className="card">
      <div className="card-title">{title}</div>
      <div style={{ fontSize: 28, fontWeight: 700, marginTop: 8 }}>{value}</div>
      {caption ? <div style={{ marginTop: 8, opacity: 0.8 }}>{caption}</div> : null}
    </section>
  );
}

function SectionCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="card">
      <h3 className="card-title">{title}</h3>
      <div style={{ marginTop: 10 }}>{children}</div>
    </section>
  );
}

function AlertsTable({ items }: { items: AlertVm[] }) {
  if (!items.length) {
    return <SectionCard title="Приоритетные алерты">Пока нет алертов для текущего контура.</SectionCard>;
  }

  return (
    <SectionCard title="Приоритетные алерты">
      <div className="table-wrap">
        <table className="table">
          <thead>
            <tr>
              <th>Название</th>
              <th>Статус</th>
              <th>Серьёзность</th>
              <th>Объект</th>
              <th>Ферма</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <tr key={item.id}>
                <td>{item.title}</td>
                <td>{item.status}</td>
                <td>{item.severity}</td>
                <td>{item.objectType}:{item.objectId}</td>
                <td>{item.farmLabel}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </SectionCard>
  );
}

function WorklistsTable({ items }: { items: WorklistVm[] }) {
  if (!items.length) {
    return <SectionCard title="Приоритетные задачи">Пока нет задач для текущего контура.</SectionCard>;
  }

  return (
    <SectionCard title="Приоритетные задачи">
      <div className="table-wrap">
        <table className="table">
          <thead>
            <tr>
              <th>Название</th>
              <th>Статус</th>
              <th>Приоритет</th>
              <th>Тип</th>
              <th>Объект</th>
              <th>Ферма</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <tr key={item.id}>
                <td>{item.title}</td>
                <td>{item.status}</td>
                <td>{item.priority}</td>
                <td>{item.worklistType}</td>
                <td>{item.objectType}:{item.objectId}</td>
                <td>{item.farmLabel}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </SectionCard>
  );
}

function EmptyState({ onRefresh }: { onRefresh: () => void }) {
  return (
    <section className="card">
      <h3 className="card-title">Сводка дня пуста, страница работает</h3>
      <div style={{ marginTop: 10 }}>
        Страница отрисовалась корректно, но runtime-данные для начала рабочего дня пока отсутствуют.
      </div>
      <div style={{ marginTop: 8 }}>
        Обычно это значит, что в runtime ещё нет записей в слоях алертов, задач или обратной связи.
      </div>
      <div style={{ marginTop: 12, display: 'flex', gap: 10, flexWrap: 'wrap' }}>
        <Link className="linked-action-card" href="/insights">
          <div>
            <div className="linked-action-title">Алерты</div>
            <div className="linked-action-caption">Проверить алерты и контракт бэкенда.</div>
          </div>
        </Link>
        <Link className="linked-action-card" href="/worklists">
          <div>
            <div className="linked-action-title">{pathLabels['/worklists']}</div>
            <div className="linked-action-caption">Убедиться, что очередь задач пуста.</div>
          </div>
        </Link>
        <button type="button" onClick={onRefresh} style={buttonStyle()}>
          Обновить
        </button>
      </div>
    </section>
  );
}

export function DailyOperationsDashboard() {
  const [data, setData] = useState<DailyOperationsViewModel | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    let cancelled = false;

    setLoading(true);
    setError(null);

    void fetchDailyOperationsBundle()
      .then((bundle) => {
        if (cancelled) return;
        setData(buildDailyOperationsViewModel(bundle));
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : 'Ошибка загрузки сводки дня');
      })
      .finally(() => {
        if (cancelled) return;
        setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [refreshKey]);

  const loadedAt = useMemo(() => {
    if (!data?.loadedAt) return '';
    try {
      return new Date(data.loadedAt).toLocaleString('ru-RU');
    } catch {
      return data.loadedAt;
    }
  }, [data?.loadedAt]);

  return (
    <div className="grid">
      <div className="topbar" style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'flex-start' }}>
        <div>
          <h1 className="page-title">Главная / сводка дня</h1>
          <p className="page-subtitle">
            Операционная сводка для начала рабочего дня.
          </p>
          {loadedAt ? <div style={{ opacity: 0.75 }}>Загружено: {loadedAt}</div> : null}
        </div>
        <button type="button" onClick={() => setRefreshKey((x) => x + 1)} style={buttonStyle()}>
          Обновить
        </button>
      </div>

      <SectionCard title="Почему это важно">
        <div>Сводка дня формируется только из канонических DTO бэкенда.</div>
        <div>Связанные действия и хуки решений управляются сервером.</div>
        <div>Пустой runtime — допустимое операционное состояние, не признак сбоя.</div>
        <div>Запросы клиента используют no-store для минимизации устаревших данных.</div>
      </SectionCard>

      {error && !data ? (
        <section className="card error-text">
          <div style={{ fontWeight: 700 }}>Ошибка загрузки сводки дня</div>
          <div style={{ marginTop: 8 }}>{error}</div>
          <div style={{ marginTop: 12 }}>
            <button type="button" onClick={() => setRefreshKey((x) => x + 1)} style={buttonStyle()}>
              Повторить
            </button>
          </div>
        </section>
      ) : null}

      {loading && !data ? <section className="card">Загружаю сводку дня…</section> : null}

      {data ? (
        <>
          {data.partialErrors.length ? (
            <section className="card">
              <h3 className="card-title">Предупреждения бэкенда</h3>
              <ul style={{ marginTop: 10, paddingLeft: 18 }}>
                {data.partialErrors.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </section>
          ) : null}

          <div className="grid grid-3">
            <MetricCard title="Открытых алертов" value={data.totals.alertsOpen} />
            <MetricCard title="Критических алертов" value={data.totals.alertsCritical} />
            <MetricCard title="Открытых задач" value={data.totals.worklistsOpen} />
            <MetricCard title="Просроченных задач" value={data.totals.worklistsOverdue} />
            <MetricCard title="Ожидают подтверждения" value={data.totals.pendingApprovals} />
            <MetricCard title="Принятие рекомендаций" value={`${Math.round(data.totals.feedbackAcceptanceRate * 100)}%`} />
          </div>

          <div className="grid grid-2">
            <SectionCard title={data.brief.title}>
              <div>{data.brief.summary}</div>
              <div style={{ marginTop: 10, opacity: 0.8 }}>{data.brief.whyNow}</div>
            </SectionCard>

            <SectionCard title="Область">
              <div>Организация: {data.scope.tenantId}</div>
              <div style={{ marginTop: 8 }}>
                Фермы: {data.scope.farms.length ? data.scope.farms.map((item) => item.label).join(', ') : '—'}
              </div>
              <div style={{ marginTop: 8 }}>
                Сайты: {data.scope.sites.length ? data.scope.sites.map((item) => item.label).join(', ') : '—'}
              </div>
            </SectionCard>
          </div>

          {data.isEmpty ? (
            <EmptyState onRefresh={() => setRefreshKey((x) => x + 1)} />
          ) : (
            <>
              {data.farms.length ? (
                <SectionCard title="Фермы / сайты">
                  <div className="table-wrap">
                    <table className="table">
                      <thead>
                        <tr>
                          <th>Ферма</th>
                          <th>Открытых алертов</th>
                          <th>Открытых задач</th>
                          <th>Просрочено</th>
                        </tr>
                      </thead>
                      <tbody>
                        {data.farms.map((item) => (
                          <tr key={item.farmId}>
                            <td>{item.label}</td>
                            <td>{item.alerts}</td>
                            <td>{item.tasks}</td>
                            <td>{item.overdue}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </SectionCard>
              ) : null}

              <SectionCard title="Связанные действия">
                <div className="linked-actions-grid">
                  <Link className="linked-action-card" href="/insights">
                    <div className="linked-action-count">{data.totals.alertsOpen}</div>
                    <div>
                      <div className="linked-action-title">Триаж алертов</div>
                      <div className="linked-action-caption">Разобрать ежедневные отклонения с объяснениями.</div>
                    </div>
                  </Link>

                  <Link className="linked-action-card" href="/worklists">
                    <div className="linked-action-count">{data.totals.worklistsOpen}</div>
                    <div>
                      <div className="linked-action-title">{pathLabels['/worklists']}</div>
                      <div className="linked-action-caption">Открыть очереди ролей и связанные задачи.</div>
                    </div>
                  </Link>

                  <Link className="linked-action-card" href="/timeline">
                    <div className="linked-action-count">{data.totals.pendingApprovals}</div>
                    <div>
                      <div className="linked-action-title">Планировщик</div>
                      <div className="linked-action-caption">Просмотр недельных планов и просроченных задач.</div>
                    </div>
                  </Link>

                  <Link className="linked-action-card" href="/decisions">
                    <div className="linked-action-count">{data.totals.linkedDecisions}</div>
                    <div>
                      <div className="linked-action-title">Журнал решений</div>
                      <div className="linked-action-caption">Управление и доказательства обратной связи.</div>
                    </div>
                  </Link>
                </div>
              </SectionCard>

              <div className="grid grid-2">
                <AlertsTable items={data.highlightAlerts} />
                <WorklistsTable items={data.highlightWorklists} />
              </div>
            </>
          )}
        </>
      ) : null}
    </div>
  );
}
