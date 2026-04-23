'use client';

import { useEffect, useState } from 'react';

import {
  fetchWeeklyBrief,
  generateWeeklyBrief,
  weeklyBriefPdfUrl,
  type BriefSection,
  type KeyRecommendation,
  type KpiEntry,
  type WeeklyAnomaly,
  type WeeklyBrief,
} from '@/lib/api/weekly-brief';

const PRIORITY_COLOR: Record<KeyRecommendation['priority'], string> = {
  high: '#ef4444',
  medium: '#f97316',
  low: '#22c55e',
};

const SEVERITY_COLOR: Record<WeeklyAnomaly['severity'], string> = {
  critical: '#ef4444',
  warning: '#f97316',
  info: '#3b82f6',
};

function PriorityBadge({ priority }: { priority: KeyRecommendation['priority'] }) {
  return (
    <span style={{
      display: 'inline-block',
      padding: '2px 8px',
      borderRadius: 4,
      fontSize: 10,
      fontWeight: 700,
      background: PRIORITY_COLOR[priority] + '22',
      color: PRIORITY_COLOR[priority],
      border: `1px solid ${PRIORITY_COLOR[priority]}55`,
      textTransform: 'uppercase',
    }}>
      {priority}
    </span>
  );
}

function SeverityBadge({ severity }: { severity: WeeklyAnomaly['severity'] }) {
  return (
    <span style={{
      display: 'inline-block',
      padding: '2px 8px',
      borderRadius: 4,
      fontSize: 10,
      fontWeight: 700,
      background: SEVERITY_COLOR[severity] + '22',
      color: SEVERITY_COLOR[severity],
      border: `1px solid ${SEVERITY_COLOR[severity]}55`,
      textTransform: 'uppercase',
    }}>
      {severity}
    </span>
  );
}

function CollapsibleSection({ title, defaultOpen = false, children }: {
  title: string;
  defaultOpen?: boolean;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div style={{ marginTop: 14 }}>
      <button
        type="button"
        onClick={() => setOpen((x) => !x)}
        style={{
          background: 'none',
          border: 'none',
          cursor: 'pointer',
          fontWeight: 700,
          fontSize: 13,
          color: 'inherit',
          padding: 0,
          display: 'flex',
          alignItems: 'center',
          gap: 6,
        }}
      >
        <span style={{ fontSize: 10 }}>{open ? '▼' : '▶'}</span>
        {title}
      </button>
      {open ? <div style={{ marginTop: 10 }}>{children}</div> : null}
    </div>
  );
}

function KpiTable({ kpiTable }: { kpiTable: Record<string, KpiEntry> }) {
  const entries = Object.entries(kpiTable).filter(([, v]) => typeof v === 'object' && v !== null);
  if (entries.length === 0) return null;
  return (
    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12, marginTop: 6 }}>
      <thead>
        <tr style={{ background: 'rgba(0,150,136,0.1)' }}>
          <th style={{ textAlign: 'left', padding: '6px 8px', fontWeight: 600 }}>Показатель</th>
          <th style={{ textAlign: 'right', padding: '6px 8px', fontWeight: 600 }}>Факт</th>
          <th style={{ textAlign: 'right', padding: '6px 8px', fontWeight: 600 }}>Пред.</th>
          <th style={{ textAlign: 'right', padding: '6px 8px', fontWeight: 600 }}>Δ%</th>
          <th style={{ textAlign: 'left', padding: '6px 8px', fontWeight: 600 }}>Ед.</th>
        </tr>
      </thead>
      <tbody>
        {entries.map(([name, kpi]) => {
          const delta = kpi.delta_pct;
          const isNeg = delta !== null && delta < 0;
          const deltaStr = delta !== null ? `${delta > 0 ? '+' : ''}${delta.toFixed(1)}%` : '—';
          return (
            <tr key={name} style={{ borderBottom: '1px solid rgba(0,0,0,0.06)' }}>
              <td style={{ padding: '5px 8px', opacity: 0.8 }}>{name}</td>
              <td style={{ padding: '5px 8px', textAlign: 'right', fontWeight: 600 }}>{kpi.value}</td>
              <td style={{ padding: '5px 8px', textAlign: 'right', opacity: 0.6 }}>{kpi.prev_period ?? '—'}</td>
              <td style={{ padding: '5px 8px', textAlign: 'right', fontWeight: 600, color: isNeg ? '#ef4444' : '#22c55e' }}>{deltaStr}</td>
              <td style={{ padding: '5px 8px', opacity: 0.6 }}>{kpi.unit}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

function SectionCard({ section }: { section: BriefSection }) {
  return (
    <div style={{ padding: '12px 14px', borderRadius: 6, background: 'rgba(0,0,0,0.02)', border: '1px solid rgba(0,0,0,0.06)', marginBottom: 8 }}>
      <div style={{ fontWeight: 700, fontSize: 13, color: '#009688', marginBottom: 6 }}>{section.heading}</div>
      <div style={{ fontSize: 12, lineHeight: 1.65, opacity: 0.85, whiteSpace: 'pre-line' }}>{section.narrative}</div>
      {section.highlights.length > 0 && (
        <ul style={{ margin: '8px 0 0', paddingLeft: 18 }}>
          {section.highlights.map((h, i) => (
            <li key={i} style={{ fontSize: 11, opacity: 0.75, marginBottom: 3 }}>{h}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

function RecommendationCard({ rec, index }: { rec: KeyRecommendation; index: number }) {
  return (
    <div style={{ padding: '10px 14px', borderRadius: 6, background: 'rgba(0,0,0,0.02)', border: '1px solid rgba(0,0,0,0.06)', marginBottom: 8 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
        <PriorityBadge priority={rec.priority} />
        <span style={{ fontSize: 12, fontWeight: 600 }}>{index}. {rec.recommendation}</span>
      </div>
      <div style={{ fontSize: 11, opacity: 0.7, marginBottom: 3 }}>
        Обоснование: {rec.rationale}
      </div>
      <div style={{ fontSize: 11, color: '#009688' }}>
        Результат: {rec.expected_outcome}
      </div>
      {rec.affected_entities.length > 0 && (
        <div style={{ fontSize: 10, opacity: 0.5, marginTop: 3 }}>
          Объекты: {rec.affected_entities.join(', ')}
        </div>
      )}
    </div>
  );
}

function AnomalyCard({ anomaly }: { anomaly: WeeklyAnomaly }) {
  return (
    <div style={{
      padding: '8px 12px',
      borderRadius: 4,
      marginBottom: 6,
      borderLeft: `3px solid ${SEVERITY_COLOR[anomaly.severity]}`,
      background: SEVERITY_COLOR[anomaly.severity] + '11',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 3 }}>
        <SeverityBadge severity={anomaly.severity} />
      </div>
      <div style={{ fontSize: 12, opacity: 0.85 }}>
        {anomaly.description}
        {anomaly.evidence_id ? (
          <span style={{ marginLeft: 6, fontSize: 10, opacity: 0.5, fontFamily: 'monospace' }}>
            [{anomaly.evidence_id}]
          </span>
        ) : null}
      </div>
    </div>
  );
}

function BriefEmpty({ onGenerate, generating }: { onGenerate: () => void; generating: boolean }) {
  return (
    <section className="card">
      <div style={{ opacity: 0.6, fontSize: 12, marginBottom: 6 }}>ИИ-помощник · Недельный брифинг</div>
      <div style={{ fontWeight: 600, fontSize: 15, marginBottom: 8 }}>
        Брифинг генерируется каждый понедельник в 07:00
      </div>
      <div style={{ opacity: 0.75, marginBottom: 12, fontSize: 13 }}>
        Еженедельный отчёт генерируется автоматически по понедельникам в 07:00 МСК.
        Вы можете создать брифинг прямо сейчас.
      </div>
      <button
        type="button"
        onClick={onGenerate}
        disabled={generating}
        style={{
          padding: '8px 16px',
          background: '#009688',
          color: '#fff',
          border: 'none',
          borderRadius: 6,
          cursor: generating ? 'not-allowed' : 'pointer',
          fontWeight: 600,
          opacity: generating ? 0.7 : 1,
        }}
      >
        {generating ? 'ИИ-помощник анализирует данные фермы…' : 'Создать брифинг фермы'}
      </button>
    </section>
  );
}

export function WeeklyBriefCard({ farmId = 'demo-farm-v1' }: { farmId?: string }) {
  const [brief, setBrief] = useState<WeeklyBrief | null>(null);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadBrief = () => {
    setLoading(true);
    setError(null);
    void fetchWeeklyBrief(farmId)
      .then(setBrief)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));
  };

  useEffect(() => { loadBrief(); }, [farmId]);

  const handleRegenerate = () => {
    setGenerating(true);
    setError(null);
    void generateWeeklyBrief(farmId)
      .then(setBrief)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setGenerating(false));
  };

  if (loading) {
    return (
      <section className="card">
        <div style={{ opacity: 0.5, fontSize: 12 }}>ИИ-помощник · Недельный брифинг</div>
        <div style={{ marginTop: 8, opacity: 0.7 }}>Загрузка брифинга…</div>
      </section>
    );
  }

  if (error || !brief) {
    return <BriefEmpty onGenerate={handleRegenerate} generating={generating} />;
  }

  const updatedAgo = (() => {
    try {
      const ms = Date.now() - new Date(brief.generated_at_utc + (brief.generated_at_utc.includes('Z') ? '' : 'Z')).getTime();
      const h = Math.floor(ms / 3600000);
      const d = Math.floor(ms / 86400000);
      if (d > 0) return `${d} дн назад`;
      if (h > 0) return `${h} ч назад`;
      return 'только что';
    } catch {
      return '';
    }
  })();

  return (
    <section className="card">
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div style={{ fontSize: 11, opacity: 0.6 }}>
          ИИ-помощник · Недельный брифинг{updatedAgo ? ` • ${updatedAgo}` : ''}
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button type="button" onClick={handleRegenerate} disabled={generating}
            title="Перегенерировать брифинг"
            style={{ background: 'none', border: '1px solid rgba(128,128,128,0.3)', borderRadius: 4, cursor: generating ? 'not-allowed' : 'pointer', padding: '3px 8px', fontSize: 12 }}>
            {generating ? '…' : '↺ Перегенерировать'}
          </button>
          <a
            href={weeklyBriefPdfUrl(brief.brief_id, farmId)}
            target="_blank"
            rel="noreferrer"
            style={{ border: '1px solid rgba(128,128,128,0.3)', borderRadius: 4, padding: '3px 8px', fontSize: 12, textDecoration: 'none', color: 'inherit' }}
          >
            PDF
          </a>
        </div>
      </div>

      {/* Title */}
      <div style={{ fontSize: 18, fontWeight: 700, marginTop: 8, lineHeight: 1.3 }}>
        {brief.title}
      </div>
      <div style={{ fontSize: 11, opacity: 0.5, marginTop: 2 }}>
        {brief.period.start} — {brief.period.end}
      </div>

      {/* Executive summary */}
      <div style={{ marginTop: 10, padding: '10px 14px', background: 'rgba(0,150,136,0.07)', borderLeft: '3px solid #009688', borderRadius: 4, fontSize: 13, lineHeight: 1.65 }}>
        {brief.executive_summary}
      </div>

      {/* KPI table */}
      {Object.keys(brief.kpi_table).length > 0 && (
        <CollapsibleSection title="KPI недели" defaultOpen>
          <KpiTable kpiTable={brief.kpi_table} />
        </CollapsibleSection>
      )}

      {/* Anomalies */}
      {brief.anomalies_detected.length > 0 && (
        <CollapsibleSection title={`Аномалии (${brief.anomalies_detected.length})`} defaultOpen>
          {brief.anomalies_detected.map((a, i) => <AnomalyCard key={i} anomaly={a} />)}
        </CollapsibleSection>
      )}

      {/* Sections */}
      {brief.sections.length > 0 && (
        <CollapsibleSection title={`Разделы отчёта (${brief.sections.length})`} defaultOpen>
          {brief.sections.map((s, i) => <SectionCard key={i} section={s} />)}
        </CollapsibleSection>
      )}

      {/* Recommendations */}
      {brief.key_recommendations.length > 0 && (
        <CollapsibleSection title={`Рекомендации (${brief.key_recommendations.length})`} defaultOpen>
          {brief.key_recommendations.map((r, i) => <RecommendationCard key={i} rec={r} index={i + 1} />)}
        </CollapsibleSection>
      )}

      {/* Footer */}
      <div style={{ marginTop: 12, fontSize: 10, opacity: 0.4 }}>
        Модель: {brief.generation_model}
        {brief.generation_tokens.input > 0
          ? ` · ${brief.generation_tokens.input}↑ / ${brief.generation_tokens.output}↓ токенов`
          : ''}
      </div>

      {error ? (
        <div style={{ marginTop: 8, color: '#ef4444', fontSize: 12 }}>{error}</div>
      ) : null}
    </section>
  );
}
