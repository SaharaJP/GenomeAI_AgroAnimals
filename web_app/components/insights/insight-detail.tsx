'use client';

import Link from 'next/link';
import { ArrowLeft, CheckCircle2, Clock } from 'lucide-react';
import { useAuth } from '@/components/auth/auth-provider';
import {
  InsightItem,
  InsightStatus,
  INSIGHT_STATUS_LABELS,
  SEVERITY_BADGE,
  SEVERITY_LABEL,
  formatRuDate,
} from '@/lib/api/insights';
import { InsightChart } from '@/components/insights/insight-chart';
import { ComparisonScale } from '@/components/insights/comparison-scale';
import { ActionChecklist } from '@/components/insights/action-checklist';

function showToast(msg: string) {
  if (typeof window === 'undefined') return;
  const el = document.createElement('div');
  el.style.cssText =
    'position:fixed;bottom:24px;right:24px;background:#0f172a;color:#fff;padding:10px 18px;border-radius:6px;font-size:13px;z-index:9999;box-shadow:0 4px 16px rgba(0,0,0,0.2)';
  el.textContent = msg;
  document.body.appendChild(el);
  setTimeout(() => el.remove(), 3000);
}

type Props = {
  insight: InsightItem;
  status: InsightStatus;
  onStatusChange: (s: InsightStatus) => void;
};

export function InsightDetail({ insight, status, onStatusChange }: Props) {
  const { me } = useAuth();
  const farmLabel = me?.scope?.active_farm_id ?? null;
  const handleTransition = (newStatus: InsightStatus) => {
    onStatusChange(newStatus);
    showToast(`Статус изменён: ${INSIGHT_STATUS_LABELS[newStatus]}`);
  };

  const handleEvidenceChipClick = (tag: string) => {
    showToast(`Доказательство: ${tag}`);
  };

  return (
    <div style={{ maxWidth: 820 }}>
      {/* Breadcrumb */}
      <div
        style={{
          marginBottom: 16,
          display: 'flex',
          alignItems: 'center',
          gap: 6,
          fontSize: 13,
          color: 'var(--text-muted)',
        }}
      >
        <Link
          href="/insights"
          style={{
            color: 'var(--accent-text)',
            display: 'inline-flex',
            alignItems: 'center',
            gap: 4,
          }}
        >
          <ArrowLeft size={13} /> Инсайты
        </Link>
        <span>›</span>
        <span
          style={{
            color: 'var(--text-secondary)',
            fontWeight: 500,
            maxWidth: 380,
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}
        >
          {insight.title}
        </span>
      </div>

      {/* Title block */}
      <div style={{ marginBottom: 24 }}>
        <div
          style={{
            display: 'flex',
            flexWrap: 'wrap',
            gap: 8,
            marginBottom: 10,
            alignItems: 'center',
          }}
        >
          <span className={`badge ${SEVERITY_BADGE[insight.severity]}`}>
            {SEVERITY_LABEL[insight.severity]}
          </span>
          {farmLabel && <span className="badge badge-teal">{farmLabel}</span>}
          {status !== insight.status ? (
            <span className="badge badge-success">{INSIGHT_STATUS_LABELS[status]}</span>
          ) : (
            <span
              className="badge"
              style={{
                background: 'var(--bg-muted)',
                color: 'var(--text-muted)',
                borderColor: 'var(--border)',
              }}
            >
              {INSIGHT_STATUS_LABELS[status]}
            </span>
          )}
        </div>

        <h1 className="page-title" style={{ marginBottom: 6 }}>
          {insight.title}
        </h1>

        <div
          style={{
            display: 'flex',
            flexWrap: 'wrap',
            gap: 6,
            alignItems: 'center',
            fontSize: 13,
            color: 'var(--text-muted)',
          }}
        >
          <span>{formatRuDate(insight.date)}</span>

          {insight.animal_ids.length > 0 && (
            <>
              <span>·</span>
              <span>
                Животные:{' '}
                {insight.animal_ids.map((id) => (
                  <Link
                    key={id}
                    href={`/profiles/animal/${id}`}
                    className="badge badge-info"
                    style={{ fontSize: 11, marginLeft: 4, textDecoration: 'none', cursor: 'pointer' }}
                    title={`Открыть карточку животного ID ${id}`}
                  >
                    ID {id}
                  </Link>
                ))}
              </span>
            </>
          )}

          {insight.tags.length > 0 && (
            <>
              <span>·</span>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                {insight.tags.map((tag) => (
                  <button
                    key={tag}
                    className="evidence-chip"
                    onClick={() => handleEvidenceChipClick(tag)}
                    title={`Источник: ${tag}`}
                  >
                    {tag}
                  </button>
                ))}
              </div>
            </>
          )}
        </div>
      </div>

      {/* Description */}
      <div className="insight-detail-section">
        <p className="insight-detail-section-title">Описание</p>
        <p className="insight-detail-body">{insight.body}</p>
        {insight.action && (
          <div style={{ marginTop: 12 }}>
            {insight.animal_ids.length > 0 ? (
              <Link
                href={`/profiles/animal/${insight.animal_ids[0]}`}
                className="insight-action"
                style={{ textDecoration: 'none', cursor: 'pointer' }}
              >
                → {insight.action}
              </Link>
            ) : (
              <span className="insight-action">→ {insight.action}</span>
            )}
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
          <button className="btn-outline" onClick={() => handleTransition('done')}>
            <CheckCircle2 size={14} />
            Закрыть
          </button>
        )}
        {status === 'done' && (
          <button className="btn-outline" onClick={() => handleTransition('to_check')}>
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
