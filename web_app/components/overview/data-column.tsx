'use client';

import { useState } from 'react';
import Link from 'next/link';
import { BarChart2, ChevronLeft, ChevronRight } from 'lucide-react';
import { DASHBOARD_METRICS } from '@/lib/api/overview';
import type { DashboardMetric } from '@/lib/api/overview';

const CHART_COLOR = '#22c55e';
const CHART_H = 110;
const CHART_PAD_X = 28;
const CHART_PAD_TOP = 8;
const CHART_PAD_BOTTOM = 18;

function MiniLineChart({ metric }: { metric: DashboardMetric }) {
  const data = metric.chartData;
  const n = data.length;
  if (n < 2) return null;

  const minV = Math.min(...data);
  const maxV = Math.max(...data);
  const range = maxV - minV || 1;

  const innerW = 100;
  const innerH = CHART_H - CHART_PAD_TOP - CHART_PAD_BOTTOM;

  const toX = (i: number) => (i / (n - 1)) * innerW;
  const toY = (v: number) => CHART_PAD_TOP + innerH - ((v - minV) / range) * innerH;

  const points = data
    .map((v, i) => `${toX(i).toFixed(1)},${toY(v).toFixed(1)}`)
    .join(' ');

  const areaPoints =
    `${toX(0).toFixed(1)},${(CHART_PAD_TOP + innerH).toFixed(1)} ` +
    points +
    ` ${toX(n - 1).toFixed(1)},${(CHART_PAD_TOP + innerH).toFixed(1)}`;

  const yLabels = [maxV, minV + range * 0.75, minV + range * 0.5, minV + range * 0.25, minV];
  const xLabels = metric.xLabels;

  return (
    <div className="mini-chart-wrap">
      <div style={{ display: 'flex' }}>
        <div className="mini-chart-yaxis">
          {yLabels.map((v, i) => (
            <span key={i}>{v.toFixed(0)}</span>
          ))}
        </div>
        <div style={{ flex: 1, position: 'relative' }}>
          <svg
            className="mini-chart-svg"
            viewBox={`0 0 100 ${CHART_H}`}
            preserveAspectRatio="none"
            aria-hidden="true"
          >
            <defs>
              <linearGradient id={`grad-${metric.id}`} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={CHART_COLOR} stopOpacity="0.18" />
                <stop offset="100%" stopColor={CHART_COLOR} stopOpacity="0.01" />
              </linearGradient>
            </defs>
            {/* grid lines */}
            {[0.25, 0.5, 0.75].map((t, i) => (
              <line
                key={i}
                x1="0" y1={(CHART_PAD_TOP + innerH * (1 - t)).toFixed(1)}
                x2="100" y2={(CHART_PAD_TOP + innerH * (1 - t)).toFixed(1)}
                stroke="var(--border)"
                strokeWidth="0.5"
              />
            ))}
            {/* area fill */}
            <polygon points={areaPoints} fill={`url(#grad-${metric.id})`} />
            {/* line */}
            <polyline
              points={points}
              fill="none"
              stroke={CHART_COLOR}
              strokeWidth="1.8"
              strokeLinejoin="round"
              strokeLinecap="round"
            />
          </svg>
        </div>
      </div>
      {xLabels.length > 0 && (
        <div className="mini-chart-xaxis">
          {xLabels.map((l, i) => (
            <span key={i}>{l}</span>
          ))}
        </div>
      )}
    </div>
  );
}

export function DataColumn() {
  const [page, setPage] = useState(0);
  const total = DASHBOARD_METRICS.length;
  const metric = DASHBOARD_METRICS[page];

  return (
    <div className="col-card">
      <div className="col-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <BarChart2 size={15} color="var(--text-secondary)" />
          <span className="col-header-title">Данные для изучения</span>
        </div>
        <div className="col-header-right">
          <button
            className="col-pagination-btn"
            onClick={() => setPage(Math.max(0, page - 1))}
            disabled={page === 0}
            aria-label="Предыдущий показатель"
          >
            <ChevronLeft size={12} />
          </button>
          <span className="col-pagination-label">{page + 1} / {total}</span>
          <button
            className="col-pagination-btn"
            onClick={() => setPage(Math.min(total - 1, page + 1))}
            disabled={page === total - 1}
            aria-label="Следующий показатель"
          >
            <ChevronRight size={12} />
          </button>
        </div>
      </div>

      <div className="col-content">
        <Link href="/analytics" style={{ textDecoration: 'none', display: 'block' }}>
          <div className="data-metric-label">{metric.headerLabel}</div>
          <div className="data-metric-title">{metric.subtitle}</div>
          <MiniLineChart metric={metric} />
        </Link>
      </div>

      <div className="col-footer">
        <Link href="/analytics" style={{ fontSize: 12, color: 'var(--accent-text)', fontWeight: 500 }}>
          Открыть аналитику →
        </Link>
      </div>
    </div>
  );
}
