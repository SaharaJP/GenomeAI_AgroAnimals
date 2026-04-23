import { Plus } from 'lucide-react';

interface Props {
  onAdd: () => void;
}

export function EmptyChartSlot({ onAdd }: Props) {
  return (
    <div className="an-empty-slot" onClick={onAdd} role="button" tabIndex={0}
      onKeyDown={e => e.key === 'Enter' && onAdd()}
    >
      {/* Pictogram: two mini chart cards stacked */}
      <div className="an-empty-pictogram" aria-hidden="true">
        <div className="an-empty-card-mock an-empty-card-back" />
        <div className="an-empty-card-mock an-empty-card-front">
          <Plus size={20} color="var(--text-muted)" />
        </div>
      </div>
      <p style={{ margin: '0 0 6px', fontWeight: 600, fontSize: 13, color: 'var(--text)' }}>
        Добавить график на эту панель
      </p>
      <span style={{ fontSize: 12, color: 'var(--accent-text)', textDecoration: 'underline', cursor: 'pointer' }}>
        Нажмите здесь, чтобы добавить
      </span>
    </div>
  );
}
