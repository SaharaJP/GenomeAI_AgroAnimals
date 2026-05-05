'use client';
import { useAnalyticsTimeseries, emptyChart } from '@/lib/api/analytics-live';
import { ChartCard } from './chart-card';
import { BiChart } from './bi-chart';
import { EmptyChartSlot } from './empty-chart-slot';
import { METRICS } from './add-chart-dialog';

interface Props {
  onAddChart: () => void;
  addedMetricIds?: string[];
  onRemoveChart?: (id: string) => void;
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

export function HerdTab({ onAddChart, addedMetricIds = [], onRemoveChart }: Props) {
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

  return (
    <div className="grid grid-2">
      <ChartCard
        title={loading ? 'Породы — загрузка…' : 'Состав по породам'}
        badges={[{ icon: '🐄', label: 'Текущий срез' }]}
        legend={breedChart?.series ?? []}
      >
        <HerdBarChart
          series={breedChart?.series ?? []}
          labels={breedChart?.labels ?? []}
        />
      </ChartCard>

      <ChartCard
        title={loading ? 'Статус стада — загрузка…' : 'Статус стада'}
        badges={[{ icon: '📊', label: 'Текущий срез' }]}
        legend={statusChart?.series ?? []}
      >
        <HerdBarChart
          series={statusChart?.series ?? []}
          labels={statusChart?.labels ?? []}
        />
      </ChartCard>

      <ChartCard
        title={loading ? 'Группы / Пены — загрузка…' : 'Распределение по группам'}
        badges={[{ icon: '🏠', label: 'По пенам' }]}
        legend={penChart?.series ?? []}
      >
        <HerdBarChart
          series={penChart?.series ?? []}
          labels={penChart?.labels ?? []}
        />
      </ChartCard>

      {addedMetricIds.map(id => {
        const metric = METRICS.find(m => m.id === id);
        return (
          <ChartCard
            key={id}
            title={metric?.name ?? id}
            badges={metric ? [{ icon: '📊', label: metric.group }] : []}
            onDelete={() => onRemoveChart?.(id)}
          >
            <div style={{ height: 140, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-muted)', fontSize: 12 }}>
              {metric?.desc ?? 'Данные загружаются…'}
            </div>
          </ChartCard>
        );
      })}

      <EmptyChartSlot onAdd={onAddChart} />
    </div>
  );
}
