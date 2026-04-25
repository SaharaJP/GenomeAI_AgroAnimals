import { getHealthMastitis, getHealthIssues } from '@/lib/api/analytics';
import { ChartCard } from './chart-card';
import { BiChart } from './bi-chart';
import { EmptyChartSlot } from './empty-chart-slot';

const mastitis     = getHealthMastitis();
const healthIssues = getHealthIssues();

interface Props {
  onAddChart: () => void;
}

export function HealthTab({ onAddChart }: Props) {
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

      <EmptyChartSlot onAdd={onAddChart} />
      <EmptyChartSlot onAdd={onAddChart} />
    </div>
  );
}
