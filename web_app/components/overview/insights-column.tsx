'use client';

import { useState } from 'react';
import { ChevronLeft, ChevronRight, Lightbulb } from 'lucide-react';
import Link from 'next/link';
import { useAuth } from '@/components/auth/auth-provider';
import { DEMO_INSIGHTS } from '@/lib/api/overview';

const SEVERITY_BADGE: Record<string, string> = {
  urgent: 'badge-danger',
  high: 'badge-warning',
  medium: 'badge-info',
  low: 'badge-success',
};

const SEVERITY_LABEL: Record<string, string> = {
  urgent: 'Срочно',
  high: 'Высокий',
  medium: 'Средний',
  low: 'Низкий',
};

function formatRuDate(dateStr: string): string {
  const d = new Date(dateStr);
  return d.toLocaleDateString('ru-RU', { day: 'numeric', month: 'long', year: 'numeric' });
}

export function InsightsColumn() {
  const { me } = useAuth();
  const farmLabel = me?.scope?.active_farm_id ?? null;
  const [page, setPage] = useState(0);
  const total = DEMO_INSIGHTS.length;
  const insight = DEMO_INSIGHTS[page];

  return (
    <div className="col-card">
      <div className="col-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <Lightbulb size={15} color="var(--text-secondary)" />
          <span className="col-header-title">Инсайты</span>
        </div>
        <div className="col-header-right">
          <button
            className="col-pagination-btn"
            onClick={() => setPage(Math.max(0, page - 1))}
            disabled={page === 0}
            aria-label="Предыдущий инсайт"
          >
            <ChevronLeft size={12} />
          </button>
          <span className="col-pagination-label">{page + 1} / {total}</span>
          <button
            className="col-pagination-btn"
            onClick={() => setPage(Math.min(total - 1, page + 1))}
            disabled={page === total - 1}
            aria-label="Следующий инсайт"
          >
            <ChevronRight size={12} />
          </button>
        </div>
      </div>

      <div className="col-content">
        <Link href={`/insights/${insight.insight_id}`} style={{ textDecoration: 'none', display: 'block' }}>
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 6 }}>
            <span className={`badge ${SEVERITY_BADGE[insight.severity] ?? ''}`}>
              {SEVERITY_LABEL[insight.severity] ?? insight.severity}
            </span>
            {farmLabel && <span className="badge badge-teal">{farmLabel}</span>}
          </div>

          <div className="insight-title">{insight.title}</div>
          <div className="insight-date">{formatRuDate(insight.date)}</div>
          <div className="insight-body">{insight.body}</div>

          {insight.action && (
            <div className="insight-action">→ {insight.action}</div>
          )}

          {(insight.farmPct !== undefined || insight.holdingPct !== undefined) && (
            <div className="comparison-bar-section">
              <div className="comparison-bar-title">
                Сравнение вашей фермы с другими: высокий показатель — слева, низкий — справа.
              </div>

              <div className="comparison-bar-row">
                <div className="comparison-bar-label-row">
                  <span>Ваша ферма</span>
                  <span>{insight.farmPct}%</span>
                </div>
                <div className="comparison-bar-track">
                  <div
                    className="comparison-bar-fill"
                    style={{ width: `${insight.farmPct}%`, background: 'var(--accent)' }}
                  />
                </div>
              </div>

              <div className="comparison-bar-row">
                <div className="comparison-bar-label-row">
                  <span>Среднее по холдингу</span>
                  <span>{insight.holdingPct}%</span>
                </div>
                <div className="comparison-bar-track">
                  <div
                    className="comparison-bar-fill"
                    style={{ width: `${insight.holdingPct}%`, background: 'var(--text-muted)' }}
                  />
                </div>
              </div>
            </div>
          )}
        </Link>
      </div>

      <div className="col-footer">
        <Link href="/decisions" style={{ fontSize: 12, color: 'var(--accent-text)', fontWeight: 500 }}>
          Все рекомендации →
        </Link>
      </div>
    </div>
  );
}
