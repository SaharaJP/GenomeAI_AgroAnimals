import {
  getReproductionRates,
  getReproductionDaysOpen,
  getReproductionVwp,
  getReproductionVwpYoungstock,
} from '@/lib/api/analytics';
import { ChartCard } from './chart-card';
import { BiChart } from './bi-chart';

const rates      = getReproductionRates();
const daysOpen   = getReproductionDaysOpen();
const vwp        = getReproductionVwp();
const youngstock = getReproductionVwpYoungstock();

export function ReproductionTab() {
  return (
    <div className="grid grid-2">
      <ChartCard
        title="Показатели воспроизводства"
        badges={[{ icon: '📊', label: 'Метрики фертильности' }, { icon: '📈', label: 'CIHMIS' }]}
        legend={rates.series}
      >
        <BiChart type="line" series={rates.series} labels={rates.labels} unit="%" />
      </ChartCard>

      <ChartCard
        title="Дней до осеменения после отёла"
        badges={[{ icon: '📊', label: 'По лактациям' }, { icon: '📈', label: 'Расчёт' }]}
        legend={daysOpen.series}
      >
        <BiChart type="line" series={daysOpen.series} labels={daysOpen.labels} unit=" д" />
      </ChartCard>

      <ChartCard
        title="Расчётный ДОС — все лактирующие коровы"
        badges={[{ icon: '📊', label: 'Серия' }, { icon: '📈', label: 'Расчёт' }]}
        legend={vwp.series}
      >
        <BiChart type="line" series={vwp.series} labels={vwp.labels} unit=" д" />
      </ChartCard>

      <ChartCard
        title="Расчётный ДОС и средний возраст первого осеменения — тёлки"
        badges={[{ icon: '📊', label: 'ДОС тёлок' }, { icon: '📈', label: 'Расчёт' }]}
        legend={youngstock.series}
      >
        <BiChart type="line" series={youngstock.series} labels={youngstock.labels} unit=" д" />
      </ChartCard>
    </div>
  );
}
