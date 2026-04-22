'use client';

import { useState } from 'react';
import Link from 'next/link';
import { ArrowLeft, CheckCircle2, Clock } from 'lucide-react';
import {
  DEMO_INSIGHTS,
  INSIGHT_STATUS_LABELS,
  InsightStatus,
  SEVERITY_BADGE,
  SEVERITY_LABEL,
  formatRuDate,
} from '@/lib/api/insights';
import { InsightChart } from '@/components/insights/insight-chart';
import { ComparisonScale } from '@/components/insights/comparison-scale';
import { ActionChecklist } from '@/components/insights/action-checklist';

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

export default function InsightDetailPage({ params }: { params: { id: string } }) {
  const insight = DEMO_INSIGHTS.find((i) => i.insight_id === params.id);
  const [status, setStatus] = useState<InsightStatus>(insight?.status ?? 'to_check');

  if (!insight) {
    return (
      <div>
        <div style={{ marginBottom: 16 }}>
          <Link href="/insights" style={{ fontSize: 13, color: 'var(--accent-text)', display: 'inline-flex', alignItems: 'center', gap: 4 }}>
            <ArrowLeft size={13} /> Инсайты
          </Link>
        </div>
        <h1 className="page-title">Инсайт не найден</h1>
        <p className="page-subtitle">Инсайт {params.id} не существует или был удалён.</p>
      </div>
    );
  }

  const handleTransition = (newStatus: InsightStatus) => {
    setStatus(newStatus);
    toast(`Статус изменён: ${INSIGHT_STATUS_LABELS[newStatus]}`);
  };

  return (
    <div style={{ maxWidth: 820 }}>
      {/* Breadcrumb */}
      <div style={{ marginBottom: 16, display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, color: 'var(--text-muted)' }}>
        <Link href="/insights" style={{ color: 'var(--accent-text)', display: 'inline-flex', alignItems: 'center', gap: 4 }}>
          <ArrowLeft size={13} /> Инсайты
        </Link>
        <span>›</span>
        <span style={{ color: 'var(--text-secondary)', fontWeight: 500, maxWidth: 300, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {insight.title}
        </span>
      </div>

      {/* Title block */}
      <div style={{ marginBottom: 24 }}>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 10, alignItems: 'center' }}>
          <span className={`badge ${SEVERITY_BADGE[insight.severity]}`}>
            {SEVERITY_LABEL[insight.severity]}
          </span>
          <span className="badge badge-teal">Демо-ферма</span>
          {status !== insight.status && (
            <span className="badge badge-success">{INSIGHT_STATUS_LABELS[status]}</span>
          )}
          {status === insight.status && (
            <span className="badge" style={{ background: 'var(--bg-muted)', color: 'var(--text-muted)', borderColor: 'var(--border)' }}>
              {INSIGHT_STATUS_LABELS[status]}
            </span>
          )}
        </div>
        <h1 className="page-title" style={{ marginBottom: 4 }}>{insight.title}</h1>
        <p style={{ fontSize: 13, color: 'var(--text-muted)', margin: 0 }}>
          {formatRuDate(insight.date)}
          {insight.animal_ids.length > 0 && (
            <> · Животные: {insight.animal_ids.join(', ')}</>
          )}
          {insight.tags.length > 0 && (
            <> · {insight.tags.join(', ')}</>
          )}
        </p>
      </div>

      {/* Description */}
      <div className="insight-detail-section">
        <p className="insight-detail-section-title">Описание</p>
        <p className="insight-detail-body">{insight.body}</p>
        {insight.action && (
          <div style={{ marginTop: 12 }}>
            <span className="insight-action">→ {insight.action}</span>
          </div>
        )}
      </div>

      {/* Chart */}
      {insight.chartData && insight.chartData.length > 0 && (
        <div className="insight-detail-section">
          <p className="insight-detail-section-title">Динамика метрики</p>
          <InsightChart
            data={insight.chartData}
            label={insight.chartLabel ?? ''}
            unit={insight.chartUnit ?? ''}
          />
        </div>
      )}

      {/* Comparison scale */}
      {insight.farmPct !== undefined && (
        <div className="insight-detail-section">
          <p className="insight-detail-section-title">Сравнение с другими фермами</p>
          <ComparisonScale farmPct={insight.farmPct} />
        </div>
      )}

      {/* Recommended actions */}
      {insight.recommendations && insight.recommendations.length > 0 && (
        <div className="insight-detail-section">
          <p className="insight-detail-section-title">Рекомендуемые действия</p>
          <ActionChecklist recommendations={insight.recommendations} />
        </div>
      )}

      {/* Action buttons */}
      <div className="insight-detail-actions">
        {status !== 'to_follow_up' && (
          <button
            className="btn-primary-teal"
            onClick={() => handleTransition('to_follow_up')}
          >
            <Clock size={14} />
            Пометить как В работе
          </button>
        )}
        {status !== 'done' && (
          <button
            className="btn-outline"
            onClick={() => handleTransition('done')}
          >
            <CheckCircle2 size={14} />
            Закрыть
          </button>
        )}
        {status === 'done' && (
          <button
            className="btn-outline"
            onClick={() => handleTransition('to_check')}
          >
            Вернуть в К проверке
          </button>
        )}
        <Link
          href="/insights"
          style={{ fontSize: 13, color: 'var(--text-muted)', marginLeft: 4 }}
        >
          ← Назад к списку
        </Link>
      </div>
    </div>
  );
}
