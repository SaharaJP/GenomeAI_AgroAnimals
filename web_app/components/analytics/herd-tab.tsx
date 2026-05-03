import { getHerdSize, getHerdDimDistribution, getHerdCalvings } from '@/lib/api/analytics';
import { ChartCard } from './chart-card';
import { BiChart } from './bi-chart';
import { EmptyChartSlot } from './empty-chart-slot';
import { METRICS } from './add-chart-dialog';

const herdSize = getHerdSize();
const dimDist  = getHerdDimDistribution();
const calvings = getHerdCalvings();

interface Props {
  onAddChart: () => void;
  addedMetricIds?: string[];
  onRemoveChart?: (id: string) => void;
}

export function HerdTab({ onAddChart, addedMetricIds = [], onRemoveChart }: Props) {
  return (
    <div className="grid grid-2">
      <ChartCard
        title="Размер стада"
        badges={[{ icon: '📊', label: 'По ферме' }]}
        legend={herdSize.series}
      >
        <BiChart type="line" series={herdSize.series} labels={herdSize.labels} unit=" гол" />
      </ChartCard>

      <ChartCard
        title="Распределение по стадиям лактации (ДДМ)"
        badges={[{ icon: '📊', label: 'По ферме' }, { icon: '📈', label: 'Стадии' }]}
        legend={dimDist.series}
      >
        <BiChart type="stacked-bar" series={dimDist.series} labels={dimDist.labels} unit="" />
      </ChartCard>

      <ChartCard
        title="Отёлы в неделю"
        badges={[{ icon: '📊', label: 'По ферме' }]}
        legend={calvings.series}
      >
        <BiChart type="line" series={calvings.series} labels={calvings.labels} unit="" />
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
