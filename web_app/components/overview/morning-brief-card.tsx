'use client';

import { useEffect, useState } from 'react';

import {
  fetchMorningBrief,
  morningBriefPdfUrl,
  regenerateMorningBrief,
  type MorningBrief,
  type TodayAction,
} from '@/lib/api/morning-brief';

const PRIORITY_COLOR: Record<TodayAction['priority'], string> = {
  high: '#ef4444',
  medium: '#f97316',
  low: '#22c55e',
};

const ROLE_LABEL: Record<TodayAction['role'], string> = {
  vet: 'Ветврач',
  zootech: 'Зоотехник',
  operator: 'Оператор',
  director: 'Директор',
};

function PriorityBadge({ priority }: { priority: TodayAction['priority'] }) {
  return (
    <span style={{
      display: 'inline-block',
      padding: '2px 8px',
      borderRadius: 4,
      fontSize: 11,
      fontWeight: 600,
      background: PRIORITY_COLOR[priority] + '22',
      color: PRIORITY_COLOR[priority],
      border: `1px solid ${PRIORITY_COLOR[priority]}55`,
    }}>
      {priority.toUpperCase()}
    </span>
  );
}

function EvidenceChip({ evidenceId }: { evidenceId: string }) {
  return (
    <span
      title={`Источник: ${evidenceId}`}
      style={{
        display: 'inline-block',
        marginLeft: 6,
        padding: '1px 6px',
        borderRadius: 3,
        fontSize: 10,
        background: 'rgba(0,150,136,0.12)',
        color: '#009688',
        border: '1px solid rgba(0,150,136,0.3)',
        cursor: 'default',
        fontFamily: 'monospace',
      }}
    >
      {evidenceId.length > 20 ? evidenceId.slice(0, 20) + '…' : evidenceId}
    </span>
  );
}

function CollapsibleSection({ title, defaultOpen = true, children }: {
  title: string;
  defaultOpen?: boolean;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div style={{ marginTop: 12 }}>
      <button
        type="button"
        onClick={() => setOpen((x) => !x)}
        style={{
          background: 'none',
          border: 'none',
          cursor: 'pointer',
          fontWeight: 600,
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
      {open ? <div style={{ marginTop: 8 }}>{children}</div> : null}
    </div>
  );
}

function BriefEmpty({ onGenerate, generating }: { onGenerate: () => void; generating: boolean }) {
  return (
    <section className="card">
      <div style={{ opacity: 0.6, fontSize: 12, marginBottom: 6 }}>ИИ-помощник</div>
      <div style={{ fontWeight: 600, fontSize: 15, marginBottom: 8 }}>Брифинг будет готов в 06:00</div>
      <div style={{ opacity: 0.75, marginBottom: 12, fontSize: 13 }}>
        Ежедневный брифинг генерируется автоматически каждое утро в 06:00 МСК.
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
        {generating ? 'Генерирую…' : 'Сгенерировать сейчас'}
      </button>
    </section>
  );
}

export function MorningBriefCard({ farmId = 'demo-farm-v1' }: { farmId?: string }) {
  const [brief, setBrief] = useState<MorningBrief | null>(null);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadBrief = () => {
    setLoading(true);
    setError(null);
    void fetchMorningBrief(farmId)
      .then(setBrief)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));
  };

  useEffect(() => { loadBrief(); }, [farmId]);

  const handleRegenerate = () => {
    setGenerating(true);
    setError(null);
    void regenerateMorningBrief(farmId)
      .then(setBrief)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setGenerating(false));
  };

  if (loading) {
    return (
      <section className="card">
        <div style={{ opacity: 0.5, fontSize: 12 }}>ИИ-помощник</div>
        <div style={{ marginTop: 8, opacity: 0.7 }}>Загрузка брифинга…</div>
      </section>
    );
  }

  if (error || !brief) {
    return <BriefEmpty onGenerate={handleRegenerate} generating={generating} />;
  }

  const updatedAgo = (() => {
    try {
      const ms = Date.now() - new Date(brief.generated_at_utc + 'Z').getTime();
      const h = Math.floor(ms / 3600000);
      const m = Math.floor((ms % 3600000) / 60000);
      if (h > 0) return `${h} ч назад`;
      if (m > 0) return `${m} мин назад`;
      return 'только что';
    } catch {
      return '';
    }
  })();

  return (
    <section className="card">
      {/* Label */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div style={{ fontSize: 11, opacity: 0.6 }}>
          ИИ-помощник{updatedAgo ? ` • обновлено ${updatedAgo}` : ''}
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button type="button" onClick={handleRegenerate} disabled={generating}
            title="Обновить брифинг"
            style={{ background: 'none', border: '1px solid rgba(128,128,128,0.3)', borderRadius: 4, cursor: generating ? 'not-allowed' : 'pointer', padding: '3px 8px', fontSize: 12 }}>
            {generating ? '…' : '↺ Обновить'}
          </button>
          <a
            href={morningBriefPdfUrl(brief.brief_id, farmId)}
            target="_blank"
            rel="noreferrer"
            style={{ border: '1px solid rgba(128,128,128,0.3)', borderRadius: 4, padding: '3px 8px', fontSize: 12, textDecoration: 'none', color: 'inherit' }}
          >
            PDF
          </a>
          <button type="button" title="Прослушать (скоро)"
            disabled
            style={{ background: 'none', border: '1px solid rgba(128,128,128,0.2)', borderRadius: 4, cursor: 'not-allowed', padding: '3px 8px', fontSize: 12, opacity: 0.4 }}>
            ♪ Слушать
          </button>
        </div>
      </div>

      {/* Headline */}
      <div style={{ fontSize: 18, fontWeight: 700, marginTop: 8, lineHeight: 1.3 }}>
        {brief.headline}
      </div>

      {/* Main takeaway */}
      <div style={{ marginTop: 8, opacity: 0.85, fontSize: 13, lineHeight: 1.6 }}>
        {brief.main_takeaway}
      </div>

      {/* Overnight changes */}
      {brief.overnight_changes.length > 0 && (
        <CollapsibleSection title="Что изменилось за ночь" defaultOpen>
          <ul style={{ margin: 0, paddingLeft: 18 }}>
            {brief.overnight_changes.map((ch, i) => (
              <li key={i} style={{ fontSize: 13, marginBottom: 6, lineHeight: 1.5 }}>
                {ch.text}
                {ch.evidence_id ? <EvidenceChip evidenceId={ch.evidence_id} /> : null}
              </li>
            ))}
          </ul>
        </CollapsibleSection>
      )}

      {/* Today actions */}
      {brief.today_actions.length > 0 && (
        <CollapsibleSection title="Требует внимания сегодня" defaultOpen>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {brief.today_actions.map((act, i) => (
              <div key={i} style={{
                display: 'flex',
                alignItems: 'flex-start',
                gap: 8,
                padding: '6px 10px',
                borderRadius: 6,
                background: 'rgba(0,0,0,0.03)',
                border: '1px solid rgba(0,0,0,0.06)',
              }}>
                <PriorityBadge priority={act.priority} />
                <div style={{ flex: 1, fontSize: 13 }}>
                  {act.action}
                  {act.due ? (
                    <span style={{ marginLeft: 8, fontSize: 11, opacity: 0.7 }}>⏰ {act.due}</span>
                  ) : null}
                </div>
                <span style={{ fontSize: 11, opacity: 0.6, whiteSpace: 'nowrap' }}>
                  {ROLE_LABEL[act.role]}
                </span>
              </div>
            ))}
          </div>
        </CollapsibleSection>
      )}

      {/* Notes */}
      {brief.notes.length > 0 && (
        <CollapsibleSection title="На заметку" defaultOpen={false}>
          <ul style={{ margin: 0, paddingLeft: 18 }}>
            {brief.notes.map((note, i) => (
              <li key={i} style={{ fontSize: 12, opacity: 0.75, marginBottom: 4 }}>{note}</li>
            ))}
          </ul>
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
