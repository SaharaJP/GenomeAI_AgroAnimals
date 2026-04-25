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
        title="Надой и ECM"
        badges={[{ icon: '📊', label: 'По ферме' }, { icon: '📈', label: 'Система доения, отгруженное молоко' }]}
        legend={milkEcm.series}
      >
        <BiChart type="line" series={milkEcm.series} labels={milkEcm.labels} unit=" кг" />
      </ChartCard>

      <ChartCard
        title="Жир и белок %"
        badges={[{ icon: '📊', label: 'По ферме' }, { icon: '📈', label: 'Контроль стада' }]}
        legend={fatProt.series}
      >
        <BiChart type="line" series={fatProt.series} labels={fatProt.labels} unit="%" />
      </ChartCard>

      <ChartCard
        title="Соматические клетки (СКК)"
        badges={[{ icon: '📊', label: 'По ферме' }, { icon: '📈', label: 'Отгруженное молоко (скорр.)' }]}
        legend={scc.series}
      >
        <BiChart type="line" series={scc.series} labels={scc.labels} unit="k" refLine={200} />
      </ChartCard>

      <EmptyChartSlot onAdd={onAddChart} />
    </div>
  );
}
