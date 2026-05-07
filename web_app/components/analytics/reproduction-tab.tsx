'use client';
import { useAnalyticsTimeseries, emptyChart } from '@/lib/api/analytics-live';
import {
  getReproductionRates,
  getReproductionDaysOpen,
  getReproductionVwp,
  getReproductionVwpYoungstock,
} from '@/lib/api/analytics';
import { ChartCard } from './chart-card';
import { BiChart } from './bi-chart';
import { EmptyChartSlot } from './empty-chart-slot';
import { MetricChartCard } from './metric-chart-card';

interface Props {
  onAddChart: () => void;
  addedMetricIds?: string[];
  onRemoveChart?: (id: string) => void;
  removedBuiltinIds?: string[];
  onRemoveBuiltin?: (key: string) => void;
  titleOverrides?: Record<string, string>;
  alertThresholds?: Record<string, string>;
  onRequestRename?: (key: string, currentTitle: string) => void;
  onRequestAlert?: (key: string, currentTitle: string) => void;
}

export function ReproductionTab({
  onAddChart,
  addedMetricIds = [],
  onRemoveChart,
  removedBuiltinIds = [],
  onRemoveBuiltin,
  titleOverrides = {},
  alertThresholds = {},
  onRequestRename,
  onRequestAlert,
}: Props) {
  const state = useAnalyticsTimeseries('reproduction');

  const inseminations = state.status === 'ok'
    ? (state.data.charts['inseminations'] ?? emptyChart('Осеменения'))
    : emptyChart('Осеменения');

  const rates = getReproductionRates();
  const daysOpen = getReproductionDaysOpen();
  const vwp = getReproductionVwp();
  const vwpYoung = getReproductionVwpYoungstock();

  const loading = state.status === 'loading';
  const isVisible = (k: string) => !removedBuiltinIds.includes(k);
  const titleOf = (k: string, def: string) => titleOverrides[k] ?? def;

  return (
    <div className="grid grid-2">
      {isVisible('inseminations') && (() => {
        const t = titleOf('inseminations', loading ? 'Осеменения — загрузка…' : 'Осеменения и стельность');
        return (
          <ChartCard
            title={t}
            badges={[{ icon: '📊', label: 'По ферме' }, { icon: '📈', label: 'Реальные данные' }]}
            legend={inseminations.series}
            alertThreshold={alertThresholds['inseminations']}
            onDelete={() => onRemoveBuiltin?.('inseminations')}
            onRename={() => onRequestRename?.('inseminations', t)}
            onAlert={() => onRequestAlert?.('inseminations', t)}
          >
            <BiChart type="line" series={inseminations.series} labels={inseminations.labels} unit=" гол" />
          </ChartCard>
        );
      })()}

      {isVisible('repro_rates') && (() => {
        const t = titleOf('repro_rates', 'Показатели воспроизводства');
        return (
          <ChartCard
            title={t}
            badges={[{ icon: '📊', label: 'По ферме' }, { icon: '%', label: 'Доли' }]}
            legend={rates.series}
            alertThreshold={alertThresholds['repro_rates']}
            onDelete={() => onRemoveBuiltin?.('repro_rates')}
            onRename={() => onRequestRename?.('repro_rates', t)}
            onAlert={() => onRequestAlert?.('repro_rates', t)}
          >
            <BiChart type="line" series={rates.series} labels={rates.labels} unit="%" />
          </ChartCard>
        );
      })()}

      {isVisible('days_open') && (() => {
        const t = titleOf('days_open', 'Дней до осеменения после отёла');
        return (
          <ChartCard
            title={t}
            badges={[{ icon: '📊', label: 'По лактациям' }]}
            legend={daysOpen.series}
            alertThreshold={alertThresholds['days_open']}
            onDelete={() => onRemoveBuiltin?.('days_open')}
            onRename={() => onRequestRename?.('days_open', t)}
            onAlert={() => onRequestAlert?.('days_open', t)}
          >
            <BiChart type="line" series={daysOpen.series} labels={daysOpen.labels} unit=" дн" />
          </ChartCard>
        );
      })()}

      {isVisible('vwp') && (() => {
        const t = titleOf('vwp', 'Расчётный ДОС (VWP)');
        return (
          <ChartCard
            title={t}
            badges={[{ icon: '📊', label: 'По лактациям' }]}
            legend={vwp.series}
            alertThreshold={alertThresholds['vwp']}
            onDelete={() => onRemoveBuiltin?.('vwp')}
            onRename={() => onRequestRename?.('vwp', t)}
            onAlert={() => onRequestAlert?.('vwp', t)}
          >
            <BiChart type="line" series={vwp.series} labels={vwp.labels} unit=" дн" />
          </ChartCard>
        );
      })()}

      {isVisible('vwp_young') && (() => {
        const t = titleOf('vwp_young', 'Возраст первого осеменения тёлок');
        return (
          <ChartCard
            title={t}
            badges={[{ icon: '🐄', label: 'Тёлки' }]}
            legend={vwpYoung.series}
            alertThreshold={alertThresholds['vwp_young']}
            onDelete={() => onRemoveBuiltin?.('vwp_young')}
            onRename={() => onRequestRename?.('vwp_young', t)}
            onAlert={() => onRequestAlert?.('vwp_young', t)}
          >
            <BiChart type="line" series={vwpYoung.series} labels={vwpYoung.labels} unit=" дн" />
          </ChartCard>
        );
      })()}

      {addedMetricIds.map((id) => (
        <MetricChartCard
          key={id}
          metricId={id}
          titleOverride={titleOverrides[id]}
          alertThreshold={alertThresholds[id]}
          onDelete={() => onRemoveChart?.(id)}
          onRename={onRequestRename}
          onAlert={onRequestAlert}
        />
      ))}

      <EmptyChartSlot onAdd={onAddChart} />
    </div>
  );
}
