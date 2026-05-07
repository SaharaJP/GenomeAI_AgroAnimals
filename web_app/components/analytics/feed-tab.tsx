'use client';
import {
  getFeedDmi,
  getFeedCost,
  getFeedEfficiency,
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
          <ChartCard
            title={t}
            badges={[{ icon: '🌾', label: 'По ферме' }, { icon: 'кг/гол', label: 'В сутки' }]}
            legend={dmi.series}
            alertThreshold={alertThresholds['dmi']}
            onDelete={() => onRemoveBuiltin?.('dmi')}
            onRename={() => onRequestRename?.('dmi', t)}
            onAlert={() => onRequestAlert?.('dmi', t)}
          >
            <BiChart type="line" series={dmi.series} labels={dmi.labels} unit=" кг" />
          </ChartCard>
        );
      })()}

      {isVisible('feed_cost') && (() => {
        const t = titleOf('feed_cost', 'Стоимость корма');
        return (
          <ChartCard
            title={t}
            badges={[{ icon: '💰', label: 'На корову/нед.' }]}
            legend={cost.series}
            alertThreshold={alertThresholds['feed_cost']}
            onDelete={() => onRemoveBuiltin?.('feed_cost')}
            onRename={() => onRequestRename?.('feed_cost', t)}
            onAlert={() => onRequestAlert?.('feed_cost', t)}
          >
            <BiChart type="line" series={cost.series} labels={cost.labels} unit=" р" />
          </ChartCard>
        );
      })()}

      {isVisible('feed_efficiency') && (() => {
        const t = titleOf('feed_efficiency', 'Эффективность кормления');
        return (
          <ChartCard
            title={t}
            badges={[{ icon: '⚖️', label: 'кг молока / кг СВ' }]}
            legend={eff.series}
            alertThreshold={alertThresholds['feed_efficiency']}
            onDelete={() => onRemoveBuiltin?.('feed_efficiency')}
            onRename={() => onRequestRename?.('feed_efficiency', t)}
            onAlert={() => onRequestAlert?.('feed_efficiency', t)}
          >
            <BiChart type="line" series={eff.series} labels={eff.labels} unit="" />
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
