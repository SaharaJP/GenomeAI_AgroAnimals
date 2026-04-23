'use client';

import type { WeeklyBrief } from '@/lib/weekly-briefs';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Mail, Download } from 'lucide-react';

const PRIORITY_TONE: Record<string, 'danger' | 'warning' | 'default'> = {
  high: 'danger',
  medium: 'warning',
  low: 'default',
};
const PRIORITY_LABEL: Record<string, string> = {
  high: 'Высокий',
  medium: 'Средний',
  low: 'Низкий',
};

function formatRu(dateStr: string): string {
  return new Date(dateStr).toLocaleDateString('ru-RU', {
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  });
}

type Props = {
  brief: WeeklyBrief;
  onSendEmail: () => void;
  onDownloadPdf: () => void;
};

export function BriefPreview({ brief, onSendEmail, onDownloadPdf }: Props) {
  return (
    <section
      className="card"
      style={{ borderLeft: '3px solid var(--accent)' }}
      aria-label="Брифинг фермы"
    >
      {/* Header */}
      <div style={{ marginBottom: 20 }}>
        <h2 className="card-title" style={{ fontSize: 18 }}>
          Брифинг фермы
        </h2>
        <p className="card-subtitle">
          {formatRu(brief.week_start)} — {formatRu(brief.week_end)}
        </p>
      </div>

      {/* KPI row */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))',
          gap: 12,
          marginBottom: 24,
        }}
      >
        {[
          { label: 'Средний удой', value: `${brief.kpis.avg_milk_yield_kg} кг` },
          { label: 'Индекс здоровья', value: `${brief.kpis.health_index_pct}%` },
          { label: 'Стельностей', value: String(brief.kpis.conceptions_confirmed) },
          { label: 'Отёлов', value: String(brief.kpis.calvings) },
        ].map((kpi) => (
          <div
            key={kpi.label}
            style={{
              padding: '12px 14px',
              background: 'var(--accent-subtle)',
              border: '1px solid var(--accent-soft)',
              borderRadius: 'var(--radius)',
              textAlign: 'center',
            }}
          >
            <div
              style={{ fontSize: 22, fontWeight: 700, color: 'var(--accent-text)', lineHeight: 1.2 }}
            >
              {kpi.value}
            </div>
            <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 4 }}>{kpi.label}</div>
          </div>
        ))}
      </div>

      {/* Narrative */}
      <div style={{ display: 'grid', gap: 10, marginBottom: 24 }}>
        {brief.narrative.map((para, i) => (
          <p key={i} style={{ margin: 0, fontSize: 14, lineHeight: 1.65, color: 'var(--text)' }}>
            {para}
          </p>
        ))}
      </div>

      {/* Key events */}
      <div style={{ marginBottom: 24 }}>
        <h3 className="section-title">Ключевые события</h3>
        <ul className="bullet-list">
          {brief.key_events.map((ev, i) => (
            <li key={i}>{ev}</li>
          ))}
        </ul>
      </div>

      {/* Recommendations */}
      <div style={{ marginBottom: 24 }}>
        <h3 className="section-title">Рекомендации</h3>
        <div style={{ display: 'grid', gap: 8 }}>
          {brief.recommendations.map((rec, i) => (
            <div
              key={i}
              style={{
                display: 'flex',
                gap: 10,
                alignItems: 'flex-start',
                padding: '10px 12px',
                background: 'var(--bg-muted)',
                borderRadius: 'var(--radius)',
                border: '1px solid var(--border)',
              }}
            >
              <Badge tone={PRIORITY_TONE[rec.priority]}>{PRIORITY_LABEL[rec.priority]}</Badge>
              <span style={{ fontSize: 13, color: 'var(--text)', lineHeight: 1.55 }}>{rec.text}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Actions */}
      <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
        <Button className="button-secondary" onClick={onSendEmail}>
          <Mail size={14} />
          Отправить на email
        </Button>
        <Button className="button-secondary" onClick={onDownloadPdf}>
          <Download size={14} />
          Скачать PDF
        </Button>
      </div>
    </section>
  );
}
