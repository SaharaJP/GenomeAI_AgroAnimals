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
    return <SectionCard title="Priority alerts">Пока нет alert-записей для текущего runtime scope.</SectionCard>;
  }

  return (
    <SectionCard title="Priority alerts">
      <div className="table-wrap">
        <table className="table">
          <thead>
            <tr>
              <th>Title</th>
              <th>Status</th>
              <th>Severity</th>
              <th>Object</th>
              <th>Farm</th>
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
    return <SectionCard title="Priority worklists">Пока нет worklist/task-записей для текущего runtime scope.</SectionCard>;
  }

  return (
    <SectionCard title="Priority worklists">
      <div className="table-wrap">
        <table className="table">
          <thead>
            <tr>
              <th>Title</th>
              <th>Status</th>
              <th>Priority</th>
              <th>Type</th>
              <th>Object</th>
              <th>Farm</th>
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
      <h3 className="card-title">Daily summary is empty, but the page is healthy</h3>
      <div style={{ marginTop: 10 }}>
        React surface отрисовался корректно, но runtime-данные для operational start-of-day пока пустые.
      </div>
      <div style={{ marginTop: 8 }}>
        Обычно это значит, что в runtime ещё нет записей в alerts/worklists/decision-feedback слоях.
      </div>
      <div style={{ marginTop: 12, display: 'flex', gap: 10, flexWrap: 'wrap' }}>
        <Link className="linked-action-card" href="/alerts">
          <div>
            <div className="linked-action-title">Open alerts</div>
            <div className="linked-action-caption">Проверить, что React route и backend contract работают.</div>
          </div>
        </Link>
        <Link className="linked-action-card" href="/worklists">
          <div>
            <div className="linked-action-title">Open worklists</div>
            <div className="linked-action-caption">Убедиться, что экран жив, но operational queue пока пуст.</div>
          </div>
        </Link>
        <button type="button" onClick={onRefresh} style={buttonStyle()}>
          Refresh page data
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
        setError(err instanceof Error ? err.message : 'Failed to load daily summary');
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
          <h1 className="page-title">Home / daily summary</h1>
          <p className="page-subtitle">
            React operational replacement surface for start-of-day workflow.
          </p>
          {loadedAt ? <div style={{ opacity: 0.75 }}>Loaded at: {loadedAt}</div> : null}
        </div>
        <button type="button" onClick={() => setRefreshKey((x) => x + 1)} style={buttonStyle()}>
          Refresh
        </button>
      </div>

      <SectionCard title="Why this matters">
        <div>The daily summary is assembled from canonical backend DTOs only.</div>
        <div>Linked actions, decision hooks and feedback hooks remain server-governed.</div>
        <div>Empty runtime is now treated as a valid operational state, not as a broken page.</div>
        <div>Client fetches use no-store + cache-bust query params to reduce stale frontend behavior.</div>
      </SectionCard>

      {error && !data ? (
        <section className="card error-text">
          <div style={{ fontWeight: 700 }}>Daily summary request failed</div>
          <div style={{ marginTop: 8 }}>{error}</div>
          <div style={{ marginTop: 12 }}>
            <button type="button" onClick={() => setRefreshKey((x) => x + 1)} style={buttonStyle()}>
              Retry
            </button>
          </div>
        </section>
      ) : null}

      {loading && !data ? <section className="card">Loading daily summary…</section> : null}

      {data ? (
        <>
          {data.partialErrors.length ? (
            <section className="card">
              <h3 className="card-title">Partial backend warnings</h3>
              <ul style={{ marginTop: 10, paddingLeft: 18 }}>
                {data.partialErrors.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </section>
          ) : null}

          <div className="grid grid-3">
            <MetricCard title="Open alerts" value={data.totals.alertsOpen} />
            <MetricCard title="Critical alerts" value={data.totals.alertsCritical} />
            <MetricCard title="Open worklists" value={data.totals.worklistsOpen} />
            <MetricCard title="Overdue worklists" value={data.totals.worklistsOverdue} />
            <MetricCard title="Pending approvals" value={data.totals.pendingApprovals} />
            <MetricCard title="Acceptance rate" value={`${Math.round(data.totals.feedbackAcceptanceRate * 100)}%`} />
          </div>

          <div className="grid grid-2">
            <SectionCard title={data.brief.title}>
              <div>{data.brief.summary}</div>
              <div style={{ marginTop: 10, opacity: 0.8 }}>{data.brief.whyNow}</div>
            </SectionCard>

            <SectionCard title="Scope summary">
              <div>Tenant: {data.scope.tenantId}</div>
              <div style={{ marginTop: 8 }}>
                Farms: {data.scope.farms.length ? data.scope.farms.map((item) => item.label).join(', ') : '—'}
              </div>
              <div style={{ marginTop: 8 }}>
                Sites: {data.scope.sites.length ? data.scope.sites.map((item) => item.label).join(', ') : '—'}
              </div>
            </SectionCard>
          </div>

          {data.isEmpty ? (
            <EmptyState onRefresh={() => setRefreshKey((x) => x + 1)} />
          ) : (
            <>
              {data.farms.length ? (
                <SectionCard title="Farm/site visibility">
                  <div className="table-wrap">
                    <table className="table">
                      <thead>
                        <tr>
                          <th>Farm</th>
                          <th>Open alerts</th>
                          <th>Open tasks</th>
                          <th>Overdue</th>
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

              <SectionCard title="Linked actions">
                <div className="linked-actions-grid">
                  <Link className="linked-action-card" href="/alerts">
                    <div className="linked-action-count">{data.totals.alertsOpen}</div>
                    <div>
                      <div className="linked-action-title">Alerts triage</div>
                      <div className="linked-action-caption">Resolve daily deviations with explainability hooks.</div>
                    </div>
                  </Link>

                  <Link className="linked-action-card" href="/worklists">
                    <div className="linked-action-count">{data.totals.worklistsOpen}</div>
                    <div>
                      <div className="linked-action-title">Worklists</div>
                      <div className="linked-action-caption">Open role queues and linked tasks.</div>
                    </div>
                  </Link>

                  <Link className="linked-action-card" href="/planner">
                    <div className="linked-action-count">{data.totals.pendingApprovals}</div>
                    <div>
                      <div className="linked-action-title">Operational planner</div>
                      <div className="linked-action-caption">Review weekly plans and overdue backlog.</div>
                    </div>
                  </Link>

                  <Link className="linked-action-card" href="/decisions">
                    <div className="linked-action-count">{data.totals.linkedDecisions}</div>
                    <div>
                      <div className="linked-action-title">Decision / feedback trail</div>
                      <div className="linked-action-caption">Open governance and feedback evidence.</div>
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
