'use client';
import {
  getFinanceRevenue,
  getFinanceFeedCost,
  getFinanceMargin,
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

export function FinanceTab({
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
  const revenue = getFinanceRevenue();
  const feedCost = getFinanceFeedCost();
  const margin = getFinanceMargin();
  const isVisible = (k: string) => !removedBuiltinIds.includes(k);
  const titleOf = (k: string, def: string) => titleOverrides[k] ?? def;

  return (
    <div className="grid grid-2">
      {isVisible('revenue') && (() => {
        const t = titleOf('revenue', 'Выручка на корову');
        return (
          <ChartCard
            title={t}
            badges={[{ icon: '💰', label: 'Нед., р/гол.' }]}
            legend={revenue.series}
            alertThreshold={alertThresholds['revenue']}
            onDelete={() => onRemoveBuiltin?.('revenue')}
            onRename={() => onRequestRename?.('revenue', t)}
            onAlert={() => onRequestAlert?.('revenue', t)}
          >
            <BiChart type="line" series={revenue.series} labels={revenue.labels} unit=" р" />
          </ChartCard>
        );
      })()}

      {isVisible('feed_cost') && (() => {
        const t = titleOf('feed_cost', 'Затраты на корм');
        return (
          <ChartCard
            title={t}
            badges={[{ icon: '🌾', label: 'Нед., р/гол.' }]}
            legend={feedCost.series}
            alertThreshold={alertThresholds['feed_cost']}
            onDelete={() => onRemoveBuiltin?.('feed_cost')}
            onRename={() => onRequestRename?.('feed_cost', t)}
            onAlert={() => onRequestAlert?.('feed_cost', t)}
          >
            <BiChart type="line" series={feedCost.series} labels={feedCost.labels} unit=" р" />
          </ChartCard>
        );
      })()}

      {isVisible('margin') && (() => {
        const t = titleOf('margin', 'Маржа на корову');
        return (
          <ChartCard
            title={t}
            badges={[{ icon: '📈', label: 'Нед., р/гол.' }]}
            legend={margin.series}
            alertThreshold={alertThresholds['margin']}
            onDelete={() => onRemoveBuiltin?.('margin')}
            onRename={() => onRequestRename?.('margin', t)}
            onAlert={() => onRequestAlert?.('margin', t)}
          >
            <BiChart type="line" series={margin.series} labels={margin.labels} unit=" р" />
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
