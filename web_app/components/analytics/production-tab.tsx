import { getProductionMilkEcm, getProductionFatProtein, getProductionScc } from '@/lib/api/analytics';
import { ChartCard } from './chart-card';
import { BiChart } from './bi-chart';
import { EmptyChartSlot } from './empty-chart-slot';
import { METRICS } from './add-chart-dialog';

const milkEcm = getProductionMilkEcm();
const fatProt = getProductionFatProtein();
const scc     = getProductionScc();

interface Props {
  onAddChart: () => void;
  addedMetricIds?: string[];
  onRemoveChart?: (id: string) => void;
}

export function ProductionTab({ onAddChart, addedMetricIds = [], onRemoveChart }: Props) {
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
