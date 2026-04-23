'use client';

import { useEffect, useState } from 'react';

import {
  fetchImpactNarrative,
  type ImpactNarrative,
  type ImpactWindow,
} from '@/lib/api/impact-narrative';
import { ImpactNarrativeSection } from './impact-narrative-section';

const WINDOW_LABELS: Record<ImpactWindow, string> = {
  '3d': '3 дня',
  '1w': '1 неделя',
  '2w': '2 недели',
  '4w': '4 недели',
};

interface TimelineEvent {
  timeline_event_id: string;
  date: string;
  event_type: string;
  title: string;
  body: string;
  animal_ids?: string[];
  impact?: string;
  impact_value?: string;
}

interface MetricCard {
  label: string;
  value: string | number;
  unit?: string;
  delta?: string;
}

interface Props {
  event: TimelineEvent;
  metrics?: MetricCard[];
  farmId?: string;
  defaultWindow?: ImpactWindow;
}

function WindowSelector({
  value,
  onChange,
}: {
  value: ImpactWindow;
  onChange: (w: ImpactWindow) => void;
}) {
  const windows: ImpactWindow[] = ['3d', '1w', '2w', '4w'];
  return (
    <div style={{ display: 'flex', gap: 4 }}>
      {windows.map((w) => (
        <button
          key={w}
          type="button"
          onClick={() => onChange(w)}
          style={{
            padding: '2px 8px',
            borderRadius: 4,
            border: `1px solid ${value === w ? '#009688' : 'rgba(0,0,0,0.15)'}`,
            background: value === w ? 'rgba(0,150,136,0.1)' : 'transparent',
            color: value === w ? '#009688' : 'inherit',
            fontSize: 11,
            fontWeight: value === w ? 600 : 400,
            cursor: 'pointer',
          }}
        >
          {WINDOW_LABELS[w]}
        </button>
      ))}
    </div>
  );
}

function MetricCardItem({ card }: { card: MetricCard }) {
  return (
    <div style={{
      padding: '8px 12px',
      borderRadius: 6,
      border: '1px solid rgba(0,0,0,0.08)',
      background: 'rgba(0,0,0,0.02)',
      minWidth: 80,
    }}>
      <div style={{ fontSize: 10, opacity: 0.55, marginBottom: 2 }}>{card.label}</div>
      <div style={{ fontSize: 16, fontWeight: 700 }}>
        {card.value}
        {card.unit ? <span style={{ fontSize: 11, fontWeight: 400, marginLeft: 2 }}>{card.unit}</span> : null}
      </div>
      {card.delta ? (
        <div style={{
          fontSize: 11,
          color: card.delta.startsWith('+') ? '#22c55e' : card.delta.startsWith('-') ? '#ef4444' : '#6b7280',
          marginTop: 1,
        }}>
          {card.delta}
        </div>
      ) : null}
    </div>
  );
}

export function ImpactPanel({ event, metrics = [], farmId = 'demo-farm-v1', defaultWindow = '1w' }: Props) {
  const [window, setWindow] = useState<ImpactWindow>(defaultWindow);
  const [narrative, setNarrative] = useState<ImpactNarrative | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadNarrative = (w: ImpactWindow) => {
    setLoading(true);
    setError(null);
    void fetchImpactNarrative({
      event_id: event.timeline_event_id,
      window: w,
      farm_id: farmId,
    })
      .then(setNarrative)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    loadNarrative(window);
  }, [event.timeline_event_id]);

  const handleWindowChange = (w: ImpactWindow) => {
    setWindow(w);
    loadNarrative(w);
  };

  return (
    <section style={{
      padding: '14px 16px',
      borderRadius: 8,
      border: '1px solid rgba(0,0,0,0.08)',
      background: 'var(--card-bg, #fff)',
    }}>
      {/* Event header */}
      <div style={{ marginBottom: 10 }}>
        <div style={{ fontSize: 11, opacity: 0.5, marginBottom: 2 }}>
          {event.date} · {event.event_type}
        </div>
        <div style={{ fontWeight: 600, fontSize: 15, lineHeight: 1.3 }}>
          {event.title}
        </div>
        {event.body && (
          <div style={{ fontSize: 12, opacity: 0.75, marginTop: 4, lineHeight: 1.5 }}>
            {event.body}
          </div>
        )}
      </div>

      {/* Metric cards */}
      {metrics.length > 0 && (
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 12 }}>
          {metrics.map((m, i) => (
            <MetricCardItem key={i} card={m} />
          ))}
        </div>
      )}

      {/* Что ещё случилось section would be injected by parent */}

      {/* AI interpretation */}
      <div style={{ borderTop: '1px solid rgba(0,0,0,0.06)', paddingTop: 12, marginTop: 4 }}>
        <div style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: 8,
          flexWrap: 'wrap',
          gap: 6,
        }}>
          <span style={{ fontSize: 12, opacity: 0.55 }}>Окно анализа</span>
          <WindowSelector value={window} onChange={handleWindowChange} />
        </div>

        {loading && (
          <div style={{ opacity: 0.5, fontSize: 13, padding: '8px 0' }}>
            Генерирую интерпретацию…
          </div>
        )}

        {error && !loading && (
          <div style={{ color: '#ef4444', fontSize: 12, padding: '4px 0' }}>
            Ошибка: {error}
            <button
              type="button"
              onClick={() => loadNarrative(window)}
              style={{ marginLeft: 8, fontSize: 11, textDecoration: 'underline', background: 'none', border: 'none', cursor: 'pointer', color: '#ef4444' }}
            >
              Повторить
            </button>
          </div>
        )}

        {narrative && !loading && (
          <ImpactNarrativeSection narrative={narrative} />
        )}
      </div>
    </section>
  );
}
