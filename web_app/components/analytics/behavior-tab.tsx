import { getBehaviorRumination, getBehaviorActivity, getBehaviorLying } from '@/lib/api/analytics';
import { ChartCard } from './chart-card';
import { BiChart } from './bi-chart';
import { EmptyChartSlot } from './empty-chart-slot';
import { METRICS } from './add-chart-dialog';

const rumination = getBehaviorRumination();
const activity   = getBehaviorActivity();
const lying      = getBehaviorLying();

interface Props {
  onAddChart: () => void;
  addedMetricIds?: string[];
  onRemoveChart?: (id: string) => void;
}

export function BehaviorTab({ onAddChart, addedMetricIds = [], onRemoveChart }: Props) {
  return (
    <div className="grid grid-2">
      <ChartCard
        title="Время жвачки"
        badges={[{ icon: '📊', label: 'По ферме' }, { icon: '📈', label: 'мин/день' }]}
        legend={rumination.series}
      >
        <BiChart type="line" series={rumination.series} labels={rumination.labels} unit=" мин" />
      </ChartCard>

      <ChartCard
        title="Индекс активности"
        badges={[{ icon: '📊', label: 'По ферме' }]}
        legend={activity.series}
      >
        <BiChart type="line" series={activity.series} labels={activity.labels} unit="" />
      </ChartCard>

      <ChartCard
        title="Время лёжки"
        badges={[{ icon: '📊', label: 'По ферме' }, { icon: '📈', label: 'ч/день' }]}
        legend={lying.series}
      >
        <BiChart type="line" series={lying.series} labels={lying.labels} unit=" ч" />
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
