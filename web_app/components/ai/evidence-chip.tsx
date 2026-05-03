'use client';

import type { EvidenceItem } from '@/lib/ai-client';

type EvidenceChipProps = {
  item: EvidenceItem;
  onClick: (item: EvidenceItem) => void;
};

export function EvidenceChip({ item, onClick }: EvidenceChipProps) {
  const label = item.cowName ? `${item.cowName} (${item.cowId})` : item.name;

  return (
    <button
      type="button"
      onClick={() => onClick(item)}
      title="Открыть детали"
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 4,
        padding: '2px 8px',
        borderRadius: 'var(--radius-pill)',
        background: 'var(--accent-soft)',
        color: 'var(--accent-text)',
        fontSize: 12,
        fontWeight: 600,
        border: '1px solid var(--accent)',
        cursor: 'pointer',
        verticalAlign: 'middle',
        whiteSpace: 'nowrap',
        lineHeight: 1.4,
        transition: 'background var(--duration-fast)',
      }}
      onMouseEnter={(e) => {
        (e.currentTarget as HTMLButtonElement).style.background = 'var(--accent)';
        (e.currentTarget as HTMLButtonElement).style.color = '#fff';
      }}
      onMouseLeave={(e) => {
        (e.currentTarget as HTMLButtonElement).style.background = 'var(--accent-soft)';
        (e.currentTarget as HTMLButtonElement).style.color = 'var(--accent-text)';
      }}
    >
      <span style={{ fontSize: 10 }}>◆</span>
      {label}
    </button>
  );
}
