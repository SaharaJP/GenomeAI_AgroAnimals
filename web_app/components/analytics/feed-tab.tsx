'use client';
import {
  getFeedDmi,
  getFeedCost,
  getFeedEfficiency,
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

export function FeedTab({
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
  const dmi = getFeedDmi();
  const cost = getFeedCost();
  const eff = getFeedEfficiency();
  const isVisible = (k: string) => !removedBuiltinIds.includes(k);
  const titleOf = (k: string, def: string) => titleOverrides[k] ?? def;

  return (
    <div className="grid grid-2">
      {isVisible('dmi') && (() => {
        const t = titleOf('dmi', 'Потребление сухого вещества (DMI)');
        return (
          <BuiltInChartCard
            metricId="dmi"
            title={t}
            badges={[{ icon: '🌾', label: 'По ферме' }, { icon: 'кг/гол', label: 'В сутки' }]}
            legend={dmi.series}
            series={dmi.series}
            labels={dmi.labels}
            isoDates={WEEK_ISO_DATES}
            unit=" кг"
            alertThreshold={alertThresholds['dmi']}
            onDelete={() => onRemoveBuiltin?.('dmi')}
            onRename={() => onRequestRename?.('dmi', t)}
            onAlert={() => onRequestAlert?.('dmi', t)}
          />
        );
      })()}

      {isVisible('feed_cost') && (() => {
        const t = titleOf('feed_cost', 'Стоимость корма');
        return (
          <BuiltInChartCard
            metricId="feed_cost"
            title={t}
            badges={[{ icon: '💰', label: 'На корову/нед.' }]}
            legend={cost.series}
            series={cost.series}
            labels={cost.labels}
            isoDates={WEEK_ISO_DATES}
            unit=" р"
            alertThreshold={alertThresholds['feed_cost']}
            onDelete={() => onRemoveBuiltin?.('feed_cost')}
            onRename={() => onRequestRename?.('feed_cost', t)}
            onAlert={() => onRequestAlert?.('feed_cost', t)}
          />
        );
      })()}

      {isVisible('feed_efficiency') && (() => {
        const t = titleOf('feed_efficiency', 'Эффективность кормления');
        return (
          <BuiltInChartCard
            metricId="feed_efficiency"
            title={t}
            badges={[{ icon: '⚖️', label: 'кг молока / кг СВ' }]}
            legend={eff.series}
            series={eff.series}
            labels={eff.labels}
            isoDates={WEEK_ISO_DATES}
            unit=""
            alertThreshold={alertThresholds['feed_efficiency']}
            onDelete={() => onRemoveBuiltin?.('feed_efficiency')}
            onRename={() => onRequestRename?.('feed_efficiency', t)}
            onAlert={() => onRequestAlert?.('feed_efficiency', t)}
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
