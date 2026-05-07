'use client';
import { Database, Activity, Rabbit, Wheat } from 'lucide-react';
import type { UploadTypeMeta } from '@/lib/api/uploads-client';

const ICONS: Record<string, React.ComponentType<{ size?: number }>> = {
  milkings: Database,
  health_events: Activity,
  animals: Rabbit,
  feed_rations: Wheat,
};

interface Props {
  types: UploadTypeMeta[];
  onSelect: (type: UploadTypeMeta) => void;
}

export function TypeGrid({ types, onSelect }: Props) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 12 }}>
      {types.map((t) => {
        const Icon = ICONS[t.type] ?? Database;
        return (
          <button
            key={t.type}
            onClick={() => onSelect(t)}
            style={{
              display: 'flex', flexDirection: 'column', alignItems: 'center',
              gap: 8, padding: 20, borderRadius: 'var(--radius-lg)',
              border: '1px solid var(--border)', background: 'var(--bg)',
              cursor: 'pointer', textAlign: 'center',
            }}
          >
            <Icon size={28} />
            <div style={{ fontWeight: 600 }}>{t.label}</div>
            <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>{t.target_table}</div>
          </button>
        );
      })}
    </div>
  );
}
