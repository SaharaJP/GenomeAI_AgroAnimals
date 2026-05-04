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

export function ProductionTab({ onAddChart, addedMetricIds = [], onRemoveChart }: Props) {
  const state = useAnalyticsTimeseries('production');

  const milkEcm = state.status === 'ok'
    ? (state.data.charts['milk_ecm'] ?? emptyChart('Надой'))
    : emptyChart('Надой');
  const fatProt = state.status === 'ok'
    ? (state.data.charts['fat_protein'] ?? emptyChart('Жир %'))
    : emptyChart('Жир %');
  const scc = state.status === 'ok'
    ? (state.data.charts['scc'] ?? emptyChart('СКК'))
    : emptyChart('СКК');

  const loading = state.status === 'loading';

  return (
    <div className="grid grid-2">
      <ChartCard
        title={loading ? 'Надой и ECM — загрузка…' : 'Надой и ECM'}
        badges={[{ icon: '📊', label: 'По ферме' }, { icon: '📈', label: 'Реальные данные' }]}
        legend={milkEcm.series}
      >
        <BiChart type="line" series={milkEcm.series} labels={milkEcm.labels} unit=" кг" />
      </ChartCard>

      <ChartCard
        title={loading ? 'Жир и белок % — загрузка…' : 'Жир и белок %'}
        badges={[{ icon: '📊', label: 'По ферме' }, { icon: '📈', label: 'Реальные данные' }]}
        legend={fatProt.series}
      >
        <BiChart type="line" series={fatProt.series} labels={fatProt.labels} unit="%" />
      </ChartCard>

      <ChartCard
        title={loading ? 'СКК — загрузка…' : 'Соматические клетки (СКК)'}
        badges={[{ icon: '📊', label: 'По ферме' }, { icon: '📈', label: 'Реальные данные' }]}
        legend={scc.series}
      >
        <BiChart type="line" series={scc.series} labels={scc.labels} unit="k" refLine={200} />
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
