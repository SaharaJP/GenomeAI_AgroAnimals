'use client';
import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { Card, MetricCard } from '@/components/ui/card';
import { FilterBar } from '@/components/ui/filter-bar';
import { FactPackGuardrailNote } from '@/components/explainability/fact-pack-guardrail-note';
import { AssistantEntryPoints } from '@/components/assistant/assistant-entry-points';
import { fetchReportsCatalog } from '@/lib/api/profiles-reports-assistant';
import type { ReportsListResponse } from '@/lib/api/contracts';

export function ReportCatalogSurface() {
  const [data, setData] = useState<ReportsListResponse | null>(null);
  const [query, setQuery] = useState('');
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void fetchReportsCatalog().then(setData).catch((err) => setError(err instanceof Error ? err.message : 'Failed to load reports'));
  }, []);

  const items = useMemo(() => {
    const rows = data?.items || [];
    if (!query) return rows;
    return rows.filter((item) => JSON.stringify(item).toLowerCase().includes(query.toLowerCase()));
  }, [data, query]);

  return (
    <div className="grid">
      <div className="topbar">
        <div>
          <h1 className="page-title">Report View</h1>
          <p className="page-subtitle">React report catalog and view surface with governance hooks and version linkage.</p>
        </div>
      </div>
      <FactPackGuardrailNote compact />
      <FilterBar placeholder="Filter reports by data_version, report_version or status…" onChange={setQuery} />
      <div className="grid grid-3">
        <MetricCard title="Visible reports" value={items.length} />
        <MetricCard title="Approved" value={items.filter((item) => item.status === 'approved').length} />
        <MetricCard title="Draft / pending" value={items.filter((item) => item.status !== 'approved').length} />
      </div>
      {error ? <div className="card error-text">{error}</div> : null}
      {!data ? <div className="card">Loading reports…</div> : (
        <>
          <Card>
            <h3 className="card-title">Reports catalog</h3>
            <div className="table-wrap">
              <table className="table">
                <thead><tr><th>Report version</th><th>Data version</th><th>Status</th><th>Approved</th><th>Actions</th></tr></thead>
                <tbody>
                  {items.map((item) => (
                    <tr key={`${item.data_version}:${item.report_version}`}>
                      <td>{item.report_version}</td>
                      <td>{item.data_version}</td>
                      <td>{item.status}</td>
                      <td>{item.approved_at || '—'}</td>
                      <td>
                        <div className="linked-inline-actions">
                          <Link href={`/reports/${encodeURIComponent(item.data_version)}/${encodeURIComponent(item.report_version)}`}>Open view</Link>
                          <Link href={`/assistant?target=report&data_version=${encodeURIComponent(item.data_version)}&report_version=${encodeURIComponent(item.report_version)}`}>Assistant</Link>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
          <AssistantEntryPoints contextLabel="reports" />
        </>
      )}
    </div>
  );
}
