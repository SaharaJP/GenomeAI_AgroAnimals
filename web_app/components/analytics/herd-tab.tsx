import { BarChart2 } from 'lucide-react';

interface Props {
  onAddChart: () => void;
  addedMetricIds?: string[];
  onRemoveChart?: (id: string) => void;
}

function ComingSoonCard({ title }: { title: string }) {
  return (
    <div className="chart-card" style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', minHeight: 180, gap: 8 }}>
      <BarChart2 size={32} color="var(--border-strong)" />
      <p style={{ margin: 0, fontWeight: 600, color: 'var(--text-secondary)' }}>{title}</p>
      <p style={{ margin: 0, fontSize: 12, color: 'var(--text-muted)' }}>Данные подключаются</p>
    </div>
  );
}

export function HerdTab({ onAddChart, addedMetricIds = [], onRemoveChart }: Props) {
  return (
    <div className="grid grid-2">
      <ComingSoonCard title="Состав стада" />
      <ComingSoonCard title="Распределение ДСД" />
      <ComingSoonCard title="Отёлы" />
    </div>
  );
}
