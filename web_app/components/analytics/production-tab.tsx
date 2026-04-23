import { getProductionMilkEcm, getProductionFatProtein, getProductionScc } from '@/lib/api/analytics';
import { ChartCard } from './chart-card';
import { BiChart } from './bi-chart';
import { EmptyChartSlot } from './empty-chart-slot';

const milkEcm = getProductionMilkEcm();
const fatProt = getProductionFatProtein();
const scc     = getProductionScc();

interface Props {
  onAddChart: () => void;
}

export function ProductionTab({ onAddChart }: Props) {
  return (
    <div className="grid grid-2">
      <ChartCard
        title="Milk yield and ECM"
        badges={[{ icon: '📊', label: 'Per farm' }, { icon: '📈', label: 'Milking system, Shipped milk' }]}
        legend={milkEcm.series}
      >
        <BiChart type="line" series={milkEcm.series} labels={milkEcm.labels} unit=" kg" />
      </ChartCard>

      <ChartCard
        title="Fat & protein %"
        badges={[{ icon: '📊', label: 'Per farm' }, { icon: '📈', label: 'Herd test' }]}
        legend={fatProt.series}
      >
        <BiChart type="line" series={fatProt.series} labels={fatProt.labels} unit="%" />
      </ChartCard>

      <ChartCard
        title="Somatic Cell Count (SCC)"
        badges={[{ icon: '📊', label: 'Per farm' }, { icon: '📈', label: 'Shipped milk (adjusted)' }]}
        legend={scc.series}
      >
        <BiChart type="line" series={scc.series} labels={scc.labels} unit="k" refLine={200} />
      </ChartCard>

      <EmptyChartSlot onAdd={onAddChart} />
    </div>
  );
}
