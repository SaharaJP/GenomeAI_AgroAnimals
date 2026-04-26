import { getFeedDmi, getFeedCost, getFeedEfficiency } from '@/lib/api/analytics';
import { ChartCard } from './chart-card';
import { BiChart } from './bi-chart';
import { EmptyChartSlot } from './empty-chart-slot';
import { METRICS } from './add-chart-dialog';

const dmi        = getFeedDmi();
const cost       = getFeedCost();
const efficiency = getFeedEfficiency();

interface Props {
  onAddChart: () => void;
  addedMetricIds?: string[];
  onRemoveChart?: (id: string) => void;
}

export function FeedTab({ onAddChart, addedMetricIds = [], onRemoveChart }: Props) {
  return (
    <div className="grid grid-2">
      <ChartCard
        title="Потребление сухого вещества (ПСВ)"
        badges={[{ icon: '📊', label: 'По ферме' }]}
        legend={dmi.series}
      >
        <BiChart type="line" series={dmi.series} labels={dmi.labels} unit=" кг" />
      </ChartCard>

      <ChartCard
        title="Стоимость корма на корову"
        badges={[{ icon: '📊', label: 'Неделя' }]}
        legend={cost.series}
      >
        <BiChart type="line" series={cost.series} labels={cost.labels} unit=" ₽" />
      </ChartCard>

      <ChartCard
        title="Эффективность кормления"
        badges={[{ icon: '📊', label: 'кг молока / кг корма' }]}
        legend={efficiency.series}
      >
        <BiChart type="line" series={efficiency.series} labels={efficiency.labels} unit=" кг/кг" />
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
