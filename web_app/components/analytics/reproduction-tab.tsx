'use client';
import { useAnalyticsTimeseries, emptyChart } from '@/lib/api/analytics-live';
import { ChartCard } from './chart-card';
import { BiChart } from './bi-chart';

export function ReproductionTab() {
  const state = useAnalyticsTimeseries('reproduction');

  const inseminations = state.status === 'ok'
    ? (state.data.charts['inseminations'] ?? emptyChart('Осеменения'))
    : emptyChart('Осеменения');

  const loading = state.status === 'loading';

  return (
    <div className="grid grid-2">
      <ChartCard
        title={loading ? 'Осеменения — загрузка…' : 'Осеменения и стельность'}
        badges={[{ icon: '📊', label: 'По ферме' }, { icon: '📈', label: 'Реальные данные' }]}
        legend={inseminations.series}
      >
        <BiChart type="line" series={inseminations.series} labels={inseminations.labels} unit=" гол" />
      </ChartCard>
    </div>
  );
}
