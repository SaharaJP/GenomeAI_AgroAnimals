'use client';
import { useAnalyticsTimeseries, emptyChart } from '@/lib/api/analytics-live';
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

export function HealthTab({
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
  const state = useAnalyticsTimeseries('health');

  const mastitis = state.status === 'ok'
    ? (state.data.charts['mastitis'] ?? emptyChart('Мастит'))
    : emptyChart('Мастит');
  const issues = state.status === 'ok' && state.data.charts['issues']?.series?.length
    ? state.data.charts['issues']
    : emptyChart('Заболевания');

  const loading = state.status === 'loading';
  const isVisible = (k: string) => !removedBuiltinIds.includes(k);
  const titleOf = (k: string, def: string) => titleOverrides[k] ?? def;

  return (
    <div className="grid grid-2">
      {isVisible('mastitis') && (() => {
        const t = titleOf('mastitis', loading ? 'Мастит — загрузка…' : 'Мастит');
        return (
          <ChartCard
            title={t}
            badges={[{ icon: '📊', label: 'По ферме' }, { icon: '📈', label: 'Реальные данные' }]}
            legend={mastitis.series}
            alertThreshold={alertThresholds['mastitis']}
            onDelete={() => onRemoveBuiltin?.('mastitis')}
            onRename={() => onRequestRename?.('mastitis', t)}
            onAlert={() => onRequestAlert?.('mastitis', t)}
          >
            <BiChart type="line" series={mastitis.series} labels={mastitis.labels} unit=" гол" />
          </ChartCard>
        );
      })()}

      {isVisible('issues') && (() => {
        const t = titleOf('issues', loading ? 'Заболевания — загрузка…' : 'Заболевания по типам');
        return (
          <ChartCard
            title={t}
            badges={[{ icon: '📊', label: 'По ферме' }, { icon: '📈', label: 'Реальные данные' }]}
            legend={issues.series}
            alertThreshold={alertThresholds['issues']}
            onDelete={() => onRemoveBuiltin?.('issues')}
            onRename={() => onRequestRename?.('issues', t)}
            onAlert={() => onRequestAlert?.('issues', t)}
          >
            <BiChart type="line" series={issues.series} labels={issues.labels} unit=" гол" />
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
