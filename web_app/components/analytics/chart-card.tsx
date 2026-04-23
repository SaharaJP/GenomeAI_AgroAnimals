import type { PropsWithChildren } from 'react';
import { Info, AlertTriangle, Trash2, Pencil } from 'lucide-react';
import type { ChartSeries } from '@/lib/api/analytics';

interface Badge {
  icon: string;
  label: string;
}

interface Props extends PropsWithChildren {
  title: string;
  badges?: Badge[];
  legend?: ChartSeries[];
  onAlert?: () => void;
  onDelete?: () => void;
  onRename?: () => void;
}

export function ChartCard({ title, badges, legend, onAlert, onDelete, onRename, children }: Props) {
  return (
    <div className="an-chart-card">
      <div className="an-chart-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, flex: 1, minWidth: 0 }}>
          <span className="an-chart-title">{title}</span>
          <Info size={12} color="var(--text-muted)" style={{ flexShrink: 0 }} />
        </div>
        <div className="an-chart-actions">
          <button className="an-chart-action-btn" title="Alert" onClick={onAlert}>
            <AlertTriangle size={11} />
          </button>
          <button className="an-chart-action-btn" title="Delete" onClick={onDelete}>
            <Trash2 size={11} />
          </button>
          <button className="an-chart-action-btn" title="Rename" onClick={onRename}>
            <Pencil size={11} />
          </button>
        </div>
      </div>

      <div className="an-chart-badges">
        {badges?.map((b, i) => (
          <span key={i} className="badge" style={{ fontSize: 10, padding: '2px 7px' }}>
            {b.icon} {b.label}
          </span>
        ))}
        {legend?.map(s => (
          <span key={s.name} style={{ display: 'inline-flex', alignItems: 'center', gap: 4, fontSize: 10, color: 'var(--text-secondary)' }}>
            <span style={{ width: 8, height: 8, borderRadius: '50%', background: s.color, display: 'inline-block', flexShrink: 0 }} />
            {s.name}
          </span>
        ))}
      </div>

      <div className="an-chart-body">
        {children}
      </div>
    </div>
  );
}
