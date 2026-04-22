'use client';

import { useState } from 'react';
import Link from 'next/link';
import { ChevronRight, Settings, Lightbulb } from 'lucide-react';
import {
  DEMO_INSIGHTS,
  InsightStatus,
  SEVERITY_BADGE,
  SEVERITY_LABEL,
  formatRuDate,
} from '@/lib/api/insights';
import { TriageTabs } from '@/components/insights/triage-tabs';

const PAGE_SIZE = 10;

function toast(msg: string) {
  if (typeof window !== 'undefined') {
    const el = document.createElement('div');
    el.style.cssText =
      'position:fixed;bottom:24px;right:24px;background:#0f172a;color:#fff;padding:10px 18px;border-radius:6px;font-size:13px;z-index:9999;box-shadow:0 4px 16px rgba(0,0,0,0.2)';
    el.textContent = msg;
    document.body.appendChild(el);
    setTimeout(() => el.remove(), 3000);
  }
}

export default function InsightsPage() {
  const [activeTab, setActiveTab] = useState<InsightStatus>('to_check');
  const [page, setPage] = useState(0);

  const counts: Record<InsightStatus, number> = {
    to_check: DEMO_INSIGHTS.filter((i) => i.status === 'to_check').length,
    to_follow_up: DEMO_INSIGHTS.filter((i) => i.status === 'to_follow_up').length,
    done: DEMO_INSIGHTS.filter((i) => i.status === 'done').length,
  };

  const filtered = DEMO_INSIGHTS.filter((i) => i.status === activeTab);
  const totalPages = Math.ceil(filtered.length / PAGE_SIZE);
  const paginated = filtered.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);

  const handleTabChange = (tab: InsightStatus) => {
    setActiveTab(tab);
    setPage(0);
  };

  return (
    <div>
      {/* Header */}
      <div className="insights-page-header">
        <div>
          <h1 className="page-title" style={{ marginBottom: 2 }}>Инсайты</h1>
          <p className="page-subtitle">Аналитические выводы и рекомендации по стаду</p>
        </div>
        <button
          className="btn-outline"
          onClick={() => toast('Настройка инсайтов — скоро будет доступна')}
        >
          <Settings size={14} />
          Настройка инсайтов
        </button>
      </div>

      {/* Tabs */}
      <TriageTabs active={activeTab} counts={counts} onChange={handleTabChange} />

      {/* Table */}
      {paginated.length === 0 ? (
        <div className="empty-state" style={{ marginTop: 40 }}>
          <Lightbulb size={32} color="var(--text-muted)" />
          <div style={{ marginTop: 12, color: 'var(--text-muted)', fontSize: 14 }}>
            Нет инсайтов в этой категории
          </div>
        </div>
      ) : (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th style={{ width: 40 }}></th>
                <th>Инсайт</th>
                <th>Ферма</th>
                <th>Период</th>
                <th style={{ width: 40 }}></th>
              </tr>
            </thead>
            <tbody>
              {paginated.map((insight) => (
                <tr
                  key={insight.insight_id}
                  style={{ cursor: 'pointer' }}
                  onClick={() => {
                    if (typeof window !== 'undefined') {
                      window.location.href = `/insights/${insight.insight_id}`;
                    }
                  }}
                >
                  {/* Unread dot (to_check items) */}
                  <td style={{ textAlign: 'center', paddingRight: 4 }}>
                    {insight.status === 'to_check' && (
                      <div className="insight-unread-dot" style={{ margin: '0 auto' }} />
                    )}
                  </td>

                  {/* Title + severity badge */}
                  <td>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                        <span className={`badge ${SEVERITY_BADGE[insight.severity]}`}>
                          {SEVERITY_LABEL[insight.severity]}
                        </span>
                        {insight.animal_ids.length > 0 && (
                          <span className="badge badge-info" style={{ fontSize: 10 }}>
                            ID {insight.animal_ids.slice(0, 2).join(', ')}
                            {insight.animal_ids.length > 2 ? ` +${insight.animal_ids.length - 2}` : ''}
                          </span>
                        )}
                      </div>
                      <span className="insight-row-title">{insight.title}</span>
                      <span className="insight-row-subtitle">{insight.body.slice(0, 80)}…</span>
                    </div>
                  </td>

                  {/* Farm */}
                  <td>
                    <span className="badge badge-teal">Демо-ферма</span>
                  </td>

                  {/* Date */}
                  <td style={{ whiteSpace: 'nowrap', fontSize: 12, color: 'var(--text-muted)' }}>
                    {formatRuDate(insight.date)}
                  </td>

                  {/* Chevron */}
                  <td>
                    <Link
                      href={`/insights/${insight.insight_id}`}
                      onClick={(e: React.MouseEvent) => e.stopPropagation()}
                      style={{ display: 'flex', alignItems: 'center', color: 'var(--text-muted)' }}
                    >
                      <ChevronRight size={16} />
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Pagination */}
      {totalPages > 1 && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 16, justifyContent: 'flex-end' }}>
          <button
            className="btn-outline"
            style={{ padding: '4px 10px', fontSize: 12 }}
            disabled={page === 0}
            onClick={() => setPage(Math.max(0, page - 1))}
          >
            ← Назад
          </button>
          <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
            {page + 1} / {totalPages}
          </span>
          <button
            className="btn-outline"
            style={{ padding: '4px 10px', fontSize: 12 }}
            disabled={page >= totalPages - 1}
            onClick={() => setPage(Math.min(totalPages - 1, page + 1))}
          >
            Вперёд →
          </button>
        </div>
      )}
    </div>
  );
}
