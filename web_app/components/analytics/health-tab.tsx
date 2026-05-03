import { getHealthMastitis, getHealthIssues } from '@/lib/api/analytics';
import { ChartCard } from './chart-card';
import { BiChart } from './bi-chart';
import { EmptyChartSlot } from './empty-chart-slot';
import { METRICS } from './add-chart-dialog';

const mastitis     = getHealthMastitis();
const healthIssues = getHealthIssues();

interface Props {
  onAddChart: () => void;
  addedMetricIds?: string[];
  onRemoveChart?: (id: string) => void;
}

export function HealthTab({ onAddChart, addedMetricIds = [], onRemoveChart }: Props) {
  return (
    <div className="grid grid-2">
      <ChartCard
        title="Коров с маститом (#)"
        badges={[{ icon: '📊', label: 'По ферме' }]}
        legend={mastitis.series}
      >
        <BiChart type="line" series={mastitis.series} labels={mastitis.labels} unit="" />
      </ChartCard>

      <ChartCard
        title="Коров с проблемами здоровья (#)"
        badges={[{ icon: '📊', label: 'Проблемы здоровья' }]}
        legend={healthIssues.series}
      >
        <BiChart type="stacked-bar" series={healthIssues.series} labels={healthIssues.labels} unit="" />
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
      {addedMetricIds.length === 0 && <EmptyChartSlot onAdd={onAddChart} />}
    </div>
  );
}
