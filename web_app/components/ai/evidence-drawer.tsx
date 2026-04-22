'use client';

import { useEffect } from 'react';
import Link from 'next/link';
import type { EvidenceItem } from '@/lib/ai-client';

type EvidenceDrawerProps = {
  item: EvidenceItem | null;
  open: boolean;
  onClose: () => void;
};

const TYPE_LABELS: Record<string, string> = {
  health_event: 'Событие здоровья',
  timeline_event: 'Событие ленты',
  culling_insight: 'Аналитика выбраковки',
  culling_candidate: 'Кандидат на выбраковку',
  reproduction_event: 'Событие воспроизводства',
  event: 'Событие',
};

export function EvidenceDrawer({ item, open, onClose }: EvidenceDrawerProps) {
  // Закрывать по Escape
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [open, onClose]);

  if (!open || !item) return null;

  const typeLabel = TYPE_LABELS[item.evidenceType] ?? item.evidenceType;

  return (
    <>
      {/* Backdrop */}
      <div
        onClick={onClose}
        style={{
          position: 'fixed',
          inset: 0,
          background: 'rgba(0,0,0,0.25)',
          zIndex: 200,
        }}
        aria-hidden="true"
      />

      {/* Drawer */}
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Детали события"
        style={{
          position: 'fixed',
          top: 0,
          right: 0,
          bottom: 0,
          width: 340,
          background: 'var(--panel)',
          boxShadow: 'var(--shadow-lg)',
          zIndex: 201,
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
        }}
      >
        {/* Header */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '16px 18px',
            borderBottom: '1px solid var(--border)',
            flexShrink: 0,
          }}
        >
          <span style={{ fontSize: 13, fontWeight: 700, color: 'var(--text)' }}>
            Детали события
          </span>
          <button
            onClick={onClose}
            aria-label="Закрыть"
            style={{
              background: 'none',
              border: 'none',
              cursor: 'pointer',
              fontSize: 18,
              color: 'var(--text-muted)',
              lineHeight: 1,
              padding: '2px 4px',
            }}
          >
            ✕
          </button>
        </div>

        {/* Content */}
        <div style={{ flex: 1, overflow: 'auto', padding: '18px' }}>
          {/* Type badge */}
          <span
            style={{
              display: 'inline-block',
              padding: '2px 8px',
              borderRadius: 'var(--radius-pill)',
              background: 'var(--accent-subtle)',
              color: 'var(--accent-text)',
              fontSize: 11,
              fontWeight: 600,
              marginBottom: 10,
            }}
          >
            {typeLabel}
          </span>

          {/* Name */}
          <div
            style={{
              fontSize: 15,
              fontWeight: 700,
              color: 'var(--text)',
              marginBottom: 8,
              lineHeight: 1.4,
            }}
          >
            {item.name}
          </div>

          {/* Cow info */}
          {item.cowName && (
            <div
              style={{
                fontSize: 12,
                color: 'var(--text-secondary)',
                marginBottom: 10,
                display: 'flex',
                alignItems: 'center',
                gap: 6,
              }}
            >
              <span>🐄</span>
              <span>
                {item.cowName}
                {item.cowId ? ` (ID: ${item.cowId})` : ''}
              </span>
            </div>
          )}

          {/* Description */}
          {item.description && (
            <div
              style={{
                fontSize: 13,
                color: 'var(--text-secondary)',
                lineHeight: 1.6,
                marginBottom: 16,
                padding: '10px 12px',
                background: 'var(--bg-muted)',
                borderRadius: 'var(--radius)',
              }}
            >
              {item.description}
            </div>
          )}

          {/* ID */}
          <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 4 }}>
            ID: <code style={{ fontFamily: 'var(--font-mono)' }}>{item.id}</code>
          </div>
        </div>

        {/* Footer actions */}
        <div
          style={{
            padding: '12px 18px',
            borderTop: '1px solid var(--border)',
            display: 'flex',
            gap: 8,
            flexShrink: 0,
          }}
        >
          {item.cowId && (
            <Link
              href={`/profiles/${item.cowId}`}
              style={{
                flex: 1,
                display: 'block',
                textAlign: 'center',
                padding: '7px 12px',
                background: 'var(--accent)',
                color: '#fff',
                borderRadius: 'var(--radius)',
                fontSize: 12,
                fontWeight: 600,
              }}
              onClick={onClose}
            >
              Перейти к профилю
            </Link>
          )}
          <Link
            href="/timeline"
            style={{
              flex: 1,
              display: 'block',
              textAlign: 'center',
              padding: '7px 12px',
              background: 'var(--bg-muted)',
              color: 'var(--text-secondary)',
              borderRadius: 'var(--radius)',
              fontSize: 12,
              fontWeight: 600,
            }}
            onClick={onClose}
          >
            В ленту событий →
          </Link>
        </div>
      </div>
    </>
  );
}
