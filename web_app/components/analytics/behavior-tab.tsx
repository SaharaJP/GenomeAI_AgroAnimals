'use client';
import {
  getBehaviorRumination,
  getBehaviorActivity,
  getBehaviorLying,
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
          <BuiltInChartCard
            metricId="rumination"
            title={t}
            badges={[{ icon: '🐄', label: 'По стаду' }]}
            legend={rumination.series}
            series={rumination.series}
            labels={rumination.labels}
            isoDates={WEEK_ISO_DATES}
            unit=" мин"
            alertThreshold={alertThresholds['rumination']}
            onDelete={() => onRemoveBuiltin?.('rumination')}
            onRename={() => onRequestRename?.('rumination', t)}
            onAlert={() => onRequestAlert?.('rumination', t)}
          />
        );
      })()}

      {isVisible('activity') && (() => {
        const t = titleOf('activity', 'Индекс активности');
        return (
          <BuiltInChartCard
            metricId="activity"
            title={t}
            badges={[{ icon: '⚡', label: 'По стаду' }]}
            legend={activity.series}
            series={activity.series}
            labels={activity.labels}
            isoDates={WEEK_ISO_DATES}
            unit=""
            alertThreshold={alertThresholds['activity']}
            onDelete={() => onRemoveBuiltin?.('activity')}
            onRename={() => onRequestRename?.('activity', t)}
            onAlert={() => onRequestAlert?.('activity', t)}
          />
        );
      })()}

      {isVisible('lying') && (() => {
        const t = titleOf('lying', 'Лёжка (часов/день)');
        return (
          <BuiltInChartCard
            metricId="lying"
            title={t}
            badges={[{ icon: '🛏️', label: 'По стаду' }]}
            legend={lying.series}
            series={lying.series}
            labels={lying.labels}
            isoDates={WEEK_ISO_DATES}
            unit=" ч"
            alertThreshold={alertThresholds['lying']}
            onDelete={() => onRemoveBuiltin?.('lying')}
            onRename={() => onRequestRename?.('lying', t)}
            onAlert={() => onRequestAlert?.('lying', t)}
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
