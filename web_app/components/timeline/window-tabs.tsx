import type { MetricWindow } from '@/lib/api/timeline';

const WINDOWS: { id: MetricWindow; label: string }[] = [
  { id: '3d', label: '3 дня' },
  { id: '1w', label: '1 неделя' },
  { id: '2w', label: '2 недели' },
  { id: '4w', label: '4 недели' },
];

type Props = {
  active: MetricWindow;
  onChange: (w: MetricWindow) => void;
};

export function WindowTabs({ active, onChange }: Props) {
  return (
    <div className="window-tabs" role="tablist" aria-label="Временной диапазон">
      {WINDOWS.map((w) => (
        <button
          key={w.id}
          className={`window-tab${active === w.id ? ' window-tab--active' : ''}`}
          role="tab"
          aria-selected={active === w.id}
          onClick={() => onChange(w.id)}
          type="button"
        >
          {w.label}
        </button>
      ))}
    </div>
  );
}
