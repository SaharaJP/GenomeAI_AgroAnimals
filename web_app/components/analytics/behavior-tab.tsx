'use client';
import {
  getBehaviorRumination,
  getBehaviorActivity,
  getBehaviorLying,
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

export function BehaviorTab({
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
  const rumination = getBehaviorRumination();
  const activity = getBehaviorActivity();
  const lying = getBehaviorLying();
  const isVisible = (k: string) => !removedBuiltinIds.includes(k);
  const titleOf = (k: string, def: string) => titleOverrides[k] ?? def;

  return (
    <div className="grid grid-2">
      {isVisible('rumination') && (() => {
        const t = titleOf('rumination', 'Жвачка (мин/день)');
        return (
          <ChartCard
            title={t}
            badges={[{ icon: '🐄', label: 'По стаду' }]}
            legend={rumination.series}
            alertThreshold={alertThresholds['rumination']}
            onDelete={() => onRemoveBuiltin?.('rumination')}
            onRename={() => onRequestRename?.('rumination', t)}
            onAlert={() => onRequestAlert?.('rumination', t)}
          >
            <BiChart type="line" series={rumination.series} labels={rumination.labels} unit=" мин" />
          </ChartCard>
        );
      })()}

      {isVisible('activity') && (() => {
        const t = titleOf('activity', 'Индекс активности');
        return (
          <ChartCard
            title={t}
            badges={[{ icon: '⚡', label: 'По стаду' }]}
            legend={activity.series}
            alertThreshold={alertThresholds['activity']}
            onDelete={() => onRemoveBuiltin?.('activity')}
            onRename={() => onRequestRename?.('activity', t)}
            onAlert={() => onRequestAlert?.('activity', t)}
          >
            <BiChart type="line" series={activity.series} labels={activity.labels} unit="" />
          </ChartCard>
        );
      })()}

      {isVisible('lying') && (() => {
        const t = titleOf('lying', 'Лёжка (часов/день)');
        return (
          <ChartCard
            title={t}
            badges={[{ icon: '🛏️', label: 'По стаду' }]}
            legend={lying.series}
            alertThreshold={alertThresholds['lying']}
            onDelete={() => onRemoveBuiltin?.('lying')}
            onRename={() => onRequestRename?.('lying', t)}
            onAlert={() => onRequestAlert?.('lying', t)}
          >
            <BiChart type="line" series={lying.series} labels={lying.labels} unit=" ч" />
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
