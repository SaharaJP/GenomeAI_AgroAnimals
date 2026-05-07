'use client';
import { useAnalyticsTimeseries, emptyChart } from '@/lib/api/analytics-live';
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

export function ProductionTab({
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
  const state = useAnalyticsTimeseries('production');

  const milkEcm = state.status === 'ok'
    ? (state.data.charts['milk_ecm'] ?? emptyChart('Надой'))
    : emptyChart('Надой');
  const fatProt = state.status === 'ok'
    ? (state.data.charts['fat_protein'] ?? emptyChart('Жир %'))
    : emptyChart('Жир %');
  const scc = state.status === 'ok'
    ? (state.data.charts['scc'] ?? emptyChart('СКК'))
    : emptyChart('СКК');

  const loading = state.status === 'loading';
  const isVisible = (k: string) => !removedBuiltinIds.includes(k);
  const titleOf = (k: string, def: string) => titleOverrides[k] ?? def;

  return (
    <div className="grid grid-2">
      {isVisible('milk_ecm') && (() => {
        const t = titleOf('milk_ecm', loading ? 'Надой и ECM — загрузка…' : 'Надой и ECM');
        return (
          <BuiltInChartCard
            metricId="milk_ecm"
            title={t}
            badges={[{ icon: '📊', label: 'По ферме' }, { icon: '📈', label: 'Реальные данные' }]}
            legend={milkEcm.series}
            series={milkEcm.series}
            labels={milkEcm.labels}
            unit=" кг"
            alertThreshold={alertThresholds['milk_ecm']}
            onDelete={() => onRemoveBuiltin?.('milk_ecm')}
            onRename={() => onRequestRename?.('milk_ecm', t)}
            onAlert={() => onRequestAlert?.('milk_ecm', t)}
          />
        );
      })()}

      {isVisible('fat_protein') && (() => {
        const t = titleOf('fat_protein', loading ? 'Жир и белок % — загрузка…' : 'Жир и белок %');
        return (
          <BuiltInChartCard
            metricId="fat_protein"
            title={t}
            badges={[{ icon: '📊', label: 'По ферме' }, { icon: '📈', label: 'Реальные данные' }]}
            legend={fatProt.series}
            series={fatProt.series}
            labels={fatProt.labels}
            unit="%"
            alertThreshold={alertThresholds['fat_protein']}
            onDelete={() => onRemoveBuiltin?.('fat_protein')}
            onRename={() => onRequestRename?.('fat_protein', t)}
            onAlert={() => onRequestAlert?.('fat_protein', t)}
          />
        );
      })()}

      {isVisible('scc') && (() => {
        const t = titleOf('scc', loading ? 'СКК — загрузка…' : 'Соматические клетки (СКК)');
        return (
          <BuiltInChartCard
            metricId="scc"
            title={t}
            badges={[{ icon: '📊', label: 'По ферме' }, { icon: '📈', label: 'Реальные данные' }]}
            legend={scc.series}
            series={scc.series}
            labels={scc.labels}
            unit="k"
            refLine={200}
            alertThreshold={alertThresholds['scc']}
            onDelete={() => onRemoveBuiltin?.('scc')}
            onRename={() => onRequestRename?.('scc', t)}
            onAlert={() => onRequestAlert?.('scc', t)}
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
