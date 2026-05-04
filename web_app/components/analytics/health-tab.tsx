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

export function HealthTab({ onAddChart, addedMetricIds = [], onRemoveChart }: Props) {
  const state = useAnalyticsTimeseries('health');

  const mastitis = state.status === 'ok'
    ? (state.data.charts['mastitis'] ?? emptyChart('Мастит'))
    : emptyChart('Мастит');
  const issues = state.status === 'ok' && state.data.charts['issues']?.series?.length
    ? state.data.charts['issues']
    : emptyChart('Заболевания');

  const loading = state.status === 'loading';

  return (
    <div className="grid grid-2">
      <ChartCard
        title={loading ? 'Мастит — загрузка…' : 'Мастит'}
        badges={[{ icon: '📊', label: 'По ферме' }, { icon: '📈', label: 'Реальные данные' }]}
        legend={mastitis.series}
      >
        <BiChart type="line" series={mastitis.series} labels={mastitis.labels} unit=" гол" />
      </ChartCard>

      <ChartCard
        title={loading ? 'Заболевания — загрузка…' : 'Заболевания по типам'}
        badges={[{ icon: '📊', label: 'По ферме' }, { icon: '📈', label: 'Реальные данные' }]}
        legend={issues.series}
      >
        <BiChart type="line" series={issues.series} labels={issues.labels} unit=" гол" />
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
