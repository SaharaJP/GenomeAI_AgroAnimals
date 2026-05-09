'use client';
import { useAnalyticsTimeseries, emptyChart } from '@/lib/api/analytics-live';
import {
  getReproductionRates,
  getReproductionDaysOpen,
  getReproductionVwp,
  getReproductionVwpYoungstock,
  WEEK_ISO_DATES,
} from '@/lib/api/analytics';
import { EmptyChartSlot } from './empty-chart-slot';
import { MetricChartCard } from './metric-chart-card';
import { BuiltInChartCard } from './built-in-chart-card';

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
          <BuiltInChartCard
            metricId="inseminations"
            title={t}
            badges={[{ icon: '📊', label: 'По ферме' }, { icon: '📈', label: 'Реальные данные' }]}
            legend={inseminations.series}
            series={inseminations.series}
            labels={inseminations.labels}
            isoDates={inseminations.iso_dates}
            unit=" гол"
            alertThreshold={alertThresholds['inseminations']}
            onDelete={() => onRemoveBuiltin?.('inseminations')}
            onRename={() => onRequestRename?.('inseminations', t)}
            onAlert={() => onRequestAlert?.('inseminations', t)}
          />
        );
      })()}

      {isVisible('repro_rates') && (() => {
        const t = titleOf('repro_rates', 'Показатели воспроизводства');
        return (
          <BuiltInChartCard
            metricId="repro_rates"
            title={t}
            badges={[{ icon: '📊', label: 'По ферме' }, { icon: '%', label: 'Доли' }]}
            legend={rates.series}
            series={rates.series}
            labels={rates.labels}
            isoDates={WEEK_ISO_DATES}
            unit="%"
            alertThreshold={alertThresholds['repro_rates']}
            onDelete={() => onRemoveBuiltin?.('repro_rates')}
            onRename={() => onRequestRename?.('repro_rates', t)}
            onAlert={() => onRequestAlert?.('repro_rates', t)}
          />
        );
      })()}

      {isVisible('days_open') && (() => {
        const t = titleOf('days_open', 'Дней до осеменения после отёла');
        return (
          <BuiltInChartCard
            metricId="days_open"
            title={t}
            badges={[{ icon: '📊', label: 'По лактациям' }]}
            legend={daysOpen.series}
            series={daysOpen.series}
            labels={daysOpen.labels}
            isoDates={WEEK_ISO_DATES}
            unit=" дн"
            alertThreshold={alertThresholds['days_open']}
            onDelete={() => onRemoveBuiltin?.('days_open')}
            onRename={() => onRequestRename?.('days_open', t)}
            onAlert={() => onRequestAlert?.('days_open', t)}
          />
        );
      })()}

      {isVisible('vwp') && (() => {
        const t = titleOf('vwp', 'Расчётный ДОС (VWP)');
        return (
          <BuiltInChartCard
            metricId="vwp"
            title={t}
            badges={[{ icon: '📊', label: 'По лактациям' }]}
            legend={vwp.series}
            series={vwp.series}
            labels={vwp.labels}
            isoDates={WEEK_ISO_DATES}
            unit=" дн"
            alertThreshold={alertThresholds['vwp']}
            onDelete={() => onRemoveBuiltin?.('vwp')}
            onRename={() => onRequestRename?.('vwp', t)}
            onAlert={() => onRequestAlert?.('vwp', t)}
          />
        );
      })()}

      {isVisible('vwp_young') && (() => {
        const t = titleOf('vwp_young', 'Возраст первого осеменения тёлок');
        return (
          <BuiltInChartCard
            metricId="vwp_young"
            title={t}
            badges={[{ icon: '🐄', label: 'Тёлки' }]}
            legend={vwpYoung.series}
            series={vwpYoung.series}
            labels={vwpYoung.labels}
            isoDates={WEEK_ISO_DATES}
            unit=" дн"
            alertThreshold={alertThresholds['vwp_young']}
            onDelete={() => onRemoveBuiltin?.('vwp_young')}
            onRename={() => onRequestRename?.('vwp_young', t)}
            onAlert={() => onRequestAlert?.('vwp_young', t)}
          />
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
