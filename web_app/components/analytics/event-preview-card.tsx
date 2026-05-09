'use client';
import { X, Calendar, Tag, FileText } from 'lucide-react';
import { useRouter } from 'next/navigation';
import type { OverlayEvent } from './analytics-overlays-context';

interface Props {
  event: OverlayEvent;
  onClose: () => void;
}

const EVENT_TYPE_LABELS: Record<string, string> = {
  mastitis_outbreak: 'Мастит',
  pen_move: 'Перевод',
  feed_change: 'Смена рациона',
  vaccination: 'Вакцинация',
  staff_change: 'Изменение персонала',
  treatment_protocol_change: 'Смена протокола',
  weather_event: 'Погодное событие',
  cull: 'Выбраковка',
  insemination: 'Осеменение',
  calving: 'Отёл',
};

function formatRu(iso: string): string {
  if (!iso) return '—';
  const d = new Date(iso.length > 10 ? iso : iso + 'T00:00:00');
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString('ru-RU', { day: 'numeric', month: 'long', year: 'numeric' });
}

export function EventPreviewCard({ event, onClose }: Props) {
  const router = useRouter();
  const typeLabel = event.event_type
    ? (EVENT_TYPE_LABELS[event.event_type] ?? event.event_type.replace(/_/g, ' '))
    : null;

  return (
    <div
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
      style={{
        position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.45)', zIndex: 250,
        display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 16,
      }}
    >
      <div
        role="dialog"
        aria-label="Предпросмотр события"
        style={{
          background: 'var(--panel)', border: '1px solid var(--border)',
          borderRadius: 'var(--radius-lg)', padding: 22, width: '100%', maxWidth: 460,
          position: 'relative',
        }}
      >
        <button
          onClick={onClose}
          aria-label="Закрыть"
          style={{ position: 'absolute', top: 12, right: 12, background: 'none', border: 'none', cursor: 'pointer' }}
        >
          <X size={18} />
        </button>

        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
          <span style={{
            display: 'inline-flex', alignItems: 'center', gap: 4,
            fontSize: 11, padding: '2px 8px', borderRadius: 4,
            background: 'var(--accent-subtle, #e0f2fe)',
            color: 'var(--accent-text, #0369a1)',
          }}>
            <Calendar size={11} /> Событие ленты
          </span>
          {typeLabel && (
            <span style={{
              display: 'inline-flex', alignItems: 'center', gap: 4,
              fontSize: 11, padding: '2px 8px', borderRadius: 4,
              background: 'var(--surface-soft, #f7f9fc)',
              color: 'var(--text-secondary)',
              border: '1px solid var(--border)',
            }}>
              <Tag size={10} /> {typeLabel}
            </span>
          )}
        </div>

        <h3 style={{ margin: '0 0 8px', fontSize: 17, lineHeight: 1.35, paddingRight: 24 }}>
          {event.title || 'Без названия'}
        </h3>

        <div style={{ marginBottom: 10, fontSize: 12, color: 'var(--text-muted)' }}>
          {formatRu(event.event_date)}
          {event.source ? ` · ${event.source}` : ''}
        </div>

        {event.body && (
          <div style={{ display: 'flex', gap: 8, alignItems: 'flex-start', marginBottom: 10 }}>
            <FileText size={14} style={{ marginTop: 2, color: 'var(--text-muted)', flexShrink: 0 }} />
            <p style={{ margin: 0, fontSize: 13, lineHeight: 1.55, color: 'var(--text)', whiteSpace: 'pre-wrap' }}>
              {event.body}
            </p>
          </div>
        )}

        {event.linked_metric_ids?.length > 0 && (
          <div style={{ marginTop: 8, marginBottom: 4, display: 'flex', flexWrap: 'wrap', gap: 4 }}>
            {event.linked_metric_ids.slice(0, 8).map((m) => (
              <span
                key={m}
                style={{
                  fontSize: 10, padding: '2px 7px', borderRadius: 10,
                  background: 'var(--surface-soft, #f3f4f6)',
                  color: 'var(--text-secondary)',
                  border: '1px solid var(--border)',
                }}
              >
                {m}
              </span>
            ))}
          </div>
        )}

        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 18 }}>
          <button className="btn-outline" onClick={onClose}>Закрыть</button>
          <button
            className="btn-primary-teal"
            onClick={() => { router.push(`/timeline?event=${encodeURIComponent(event.event_id)}`); onClose(); }}
          >
            Открыть в ленте
          </button>
        </div>
      </div>
    </div>
  );
}
