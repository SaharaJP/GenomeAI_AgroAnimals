'use client';
import { useAnalyticsTimeseries, emptyChart } from '@/lib/api/analytics-live';
import { ChartCard } from './chart-card';
import { BiChart } from './bi-chart';
import { EmptyChartSlot } from './empty-chart-slot';
import { MetricChartCard } from './metric-chart-card';

interface Props {
  onAddChart: () => void;
  addedMetricIds?: string[];
  onRemoveChart?: (id: string) => void;
  removedBuiltinIds?: string[];
  onRemoveBuiltin?: (key: string) => void;
  titleOverrides?: Record<string, string>;
  alertThresholds?: Record<string, string>;
  onRequestRename?: (key: string, currentTitle: string) => void;
  onRequestAlert?: (key: string, currentTitle: string) => void;
}

function HerdBarChart({ series, labels }: { series: { name: string; color: string; data: number[] }[]; labels: string[] }) {
  if (!series.length || !labels.length) {
    return (
      <div style={{ height: 140, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-muted)', fontSize: 12 }}>
        Нет данных
      </div>
    );
  }

  const total = series.reduce((sum, s) => sum + (s.data[0] ?? 0), 0);
  if (total === 0) {
    return (
      <div style={{ height: 140, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-muted)', fontSize: 12 }}>
        Нет данных
      </div>
    );
  }

  return (
    <div style={{ padding: '8px 0' }}>
      {series.map((s) => {
        const val = s.data[0] ?? 0;
        const pct = total > 0 ? (val / total) * 100 : 0;
        return (
          <div key={s.name} style={{ marginBottom: 8 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, marginBottom: 3 }}>
              <span style={{ color: 'var(--text-secondary)', fontWeight: 500 }}>{s.name}</span>
              <span style={{ color: 'var(--text-muted)' }}>{val} гол. ({pct.toFixed(1)}%)</span>
            </div>
            <div style={{ height: 8, background: 'var(--border)', borderRadius: 4, overflow: 'hidden' }}>
              <div style={{ height: '100%', width: `${pct}%`, background: s.color, borderRadius: 4, transition: 'width 0.4s ease' }} />
            </div>
          </div>
        );
      })}
    </div>
  );
}

export function HerdTab({
  onAddChart,
  addedMetricIds = [],
  onRemoveChart,
  removedBuiltinIds = [],
  onRemoveBuiltin,
  titleOverrides = {},
  alertThresholds = {},
  onRequestRename,
  onRequestAlert,
}: Props) {
  const state = useAnalyticsTimeseries('herd');

  const breedChart = state.status === 'ok'
    ? (state.data.charts['breed_distribution'] ?? null)
    : null;
  const statusChart = state.status === 'ok'
    ? (state.data.charts['status_distribution'] ?? null)
    : null;
  const penChart = state.status === 'ok'
    ? (state.data.charts['pen_distribution'] ?? null)
    : null;

  const loading = state.status === 'loading';
  const isVisible = (k: string) => !removedBuiltinIds.includes(k);
  const titleOf = (k: string, def: string) => titleOverrides[k] ?? def;

  return (
    <div className="grid grid-2">
      {isVisible('breed_distribution') && (() => {
        const t = titleOf('breed_distribution', loading ? 'Породы — загрузка…' : 'Состав по породам');
        return (
          <ChartCard
            title={t}
            badges={[{ icon: '🐄', label: 'Текущий срез' }]}
            legend={breedChart?.series ?? []}
            alertThreshold={alertThresholds['breed_distribution']}
            onDelete={() => onRemoveBuiltin?.('breed_distribution')}
            onRename={() => onRequestRename?.('breed_distribution', t)}
            onAlert={() => onRequestAlert?.('breed_distribution', t)}
          >
            <HerdBarChart series={breedChart?.series ?? []} labels={breedChart?.labels ?? []} />
          </ChartCard>
        );
      })()}

      {isVisible('status_distribution') && (() => {
        const t = titleOf('status_distribution', loading ? 'Статус стада — загрузка…' : 'Статус стада');
        return (
          <ChartCard
            title={t}
            badges={[{ icon: '📊', label: 'Текущий срез' }]}
            legend={statusChart?.series ?? []}
            alertThreshold={alertThresholds['status_distribution']}
            onDelete={() => onRemoveBuiltin?.('status_distribution')}
            onRename={() => onRequestRename?.('status_distribution', t)}
            onAlert={() => onRequestAlert?.('status_distribution', t)}
          >
            <HerdBarChart series={statusChart?.series ?? []} labels={statusChart?.labels ?? []} />
          </ChartCard>
        );
      })()}

      {isVisible('pen_distribution') && (() => {
        const t = titleOf('pen_distribution', loading ? 'Группы / Пены — загрузка…' : 'Распределение по группам');
        return (
          <ChartCard
            title={t}
            badges={[{ icon: '🏠', label: 'По пенам' }]}
            legend={penChart?.series ?? []}
            alertThreshold={alertThresholds['pen_distribution']}
            onDelete={() => onRemoveBuiltin?.('pen_distribution')}
            onRename={() => onRequestRename?.('pen_distribution', t)}
            onAlert={() => onRequestAlert?.('pen_distribution', t)}
          >
            <HerdBarChart series={penChart?.series ?? []} labels={penChart?.labels ?? []} />
          </ChartCard>
        );
      })()}

      {addedMetricIds.map((id) => (
        <MetricChartCard
          key={id}
          metricId={id}
          titleOverride={titleOverrides[id]}
          alertThreshold={alertThresholds[id]}
          onDelete={() => onRemoveChart?.(id)}
          onRename={onRequestRename}
          onAlert={onRequestAlert}
        />
      ))}

      <EmptyChartSlot onAdd={onAddChart} />
    </div>
  );
}
