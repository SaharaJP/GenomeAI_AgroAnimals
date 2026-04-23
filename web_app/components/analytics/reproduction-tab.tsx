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
        title="Reproduction rates"
        badges={[{ icon: '📊', label: 'Fertility metrics' }, { icon: '📈', label: 'CIHMIS' }]}
        legend={rates.series}
      >
        <BiChart type="line" series={rates.series} labels={rates.labels} unit="%" />
      </ChartCard>

      <ChartCard
        title="Days open after calving"
        badges={[{ icon: '📊', label: 'Per lactation' }, { icon: '📈', label: 'Calculation' }]}
        legend={daysOpen.series}
      >
        <BiChart type="line" series={daysOpen.series} labels={daysOpen.labels} unit=" d" />
      </ChartCard>

      <ChartCard
        title="Calculated VWP — all lactating cows"
        badges={[{ icon: '📊', label: 'Series' }, { icon: '📈', label: 'Calculation' }]}
        legend={vwp.series}
      >
        <BiChart type="line" series={vwp.series} labels={vwp.labels} unit=" d" />
      </ChartCard>

      <ChartCard
        title="Calculated VWP and avg age at first breeding — youngstock"
        badges={[{ icon: '📊', label: 'Youngstock VWP' }, { icon: '📈', label: 'Calculation' }]}
        legend={youngstock.series}
      >
        <BiChart type="line" series={youngstock.series} labels={youngstock.labels} unit=" d" />
      </ChartCard>
    </div>
  );
}
