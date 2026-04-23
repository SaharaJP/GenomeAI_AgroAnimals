'use client';

import { Card } from '@/components/ui/card';

type Props = {
  enabled: boolean;
  onToggle: (v: boolean) => void;
};

export function SettingsCard({ enabled, onToggle }: Props) {
  return (
    <Card>
      <h2 className="card-title">Настройки</h2>
      <label
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 14,
          cursor: 'pointer',
          marginTop: 12,
          userSelect: 'none',
        }}
      >
        {/* Toggle track */}
        <span
          style={{ position: 'relative', display: 'inline-block', width: 38, height: 22, flexShrink: 0 }}
        >
          <input
            type="checkbox"
            checked={enabled}
            onChange={(e) => onToggle(e.target.checked)}
            style={{ position: 'absolute', opacity: 0, width: 0, height: 0 }}
            aria-label="Еженедельный email-брифинг"
          />
          <span
            style={{
              position: 'absolute',
              inset: 0,
              background: enabled ? 'var(--accent)' : '#d1d5db',
              borderRadius: 11,
              transition: 'background 0.2s ease',
            }}
          />
          <span
            style={{
              position: 'absolute',
              left: enabled ? 18 : 2,
              top: 3,
              width: 16,
              height: 16,
              background: 'white',
              borderRadius: '50%',
              transition: 'left 0.2s ease',
              boxShadow: '0 1px 3px rgba(0,0,0,0.15)',
            }}
          />
        </span>
        <span style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.55 }}>
          Включите, чтобы получать email с брифингом фермы каждый понедельник о Демо-ферме
        </span>
      </label>
    </Card>
  );
}
