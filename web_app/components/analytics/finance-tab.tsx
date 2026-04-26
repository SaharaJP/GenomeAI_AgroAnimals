import { getFinanceRevenue, getFinanceFeedCost, getFinanceMargin } from '@/lib/api/analytics';
import { ChartCard } from './chart-card';
import { BiChart } from './bi-chart';
import { EmptyChartSlot } from './empty-chart-slot';
import { METRICS } from './add-chart-dialog';

const revenue  = getFinanceRevenue();
const feedCost = getFinanceFeedCost();
const margin   = getFinanceMargin();

interface Props {
  onAddChart: () => void;
  addedMetricIds?: string[];
  onRemoveChart?: (id: string) => void;
}

export function FinanceTab({ onAddChart, addedMetricIds = [], onRemoveChart }: Props) {
  return (
    <div className="grid grid-2">
      <ChartCard
        title="Выручка на корову"
        badges={[{ icon: '📊', label: 'По ферме' }, { icon: '📈', label: 'Месяц' }]}
        legend={revenue.series}
      >
        <BiChart type="line" series={revenue.series} labels={revenue.labels} unit=" ₽" />
      </ChartCard>

      <ChartCard
        title="Затраты на корм"
        badges={[{ icon: '📊', label: 'По ферме' }, { icon: '📈', label: 'Месяц' }]}
        legend={feedCost.series}
      >
        <BiChart type="line" series={feedCost.series} labels={feedCost.labels} unit=" ₽" />
      </ChartCard>

      <ChartCard
        title="Маржа на корову"
        badges={[{ icon: '📊', label: 'По ферме' }, { icon: '📈', label: 'Месяц' }]}
        legend={margin.series}
      >
        <BiChart type="line" series={margin.series} labels={margin.labels} unit=" ₽" />
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
