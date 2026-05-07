'use client';
import { getWeatherThi, getWeatherTemp, getWeatherHumidity } from '@/lib/api/analytics';
import { ChartCard } from './chart-card';
import { BiChart } from './bi-chart';
import { EmptyChartSlot } from './empty-chart-slot';
import { MetricChartCard } from './metric-chart-card';

const thi      = getWeatherThi();
const temp     = getWeatherTemp();
const humidity = getWeatherHumidity();

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

export function WeatherTab({
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
  const isVisible = (k: string) => !removedBuiltinIds.includes(k);
  const titleOf = (k: string, def: string) => titleOverrides[k] ?? def;

  return (
    <div className="grid grid-2">
      {isVisible('thi') && (() => {
        const t = titleOf('thi', 'Индекс тепловой нагрузки (ТГИ)');
        return (
          <ChartCard
            title={t}
            badges={[{ icon: '🌡️', label: 'По ферме' }, { icon: '⚠️', label: 'Порог: 72' }]}
            legend={thi.series}
            alertThreshold={alertThresholds['thi']}
            onDelete={() => onRemoveBuiltin?.('thi')}
            onRename={() => onRequestRename?.('thi', t)}
            onAlert={() => onRequestAlert?.('thi', t)}
          >
            <BiChart type="line" series={thi.series} labels={thi.labels} unit="" refLine={72} />
          </ChartCard>
        );
      })()}

      {isVisible('temp') && (() => {
        const t = titleOf('temp', 'Температура воздуха');
        return (
          <ChartCard
            title={t}
            badges={[{ icon: '🌡️', label: 'По ферме' }]}
            legend={temp.series}
            alertThreshold={alertThresholds['temp']}
            onDelete={() => onRemoveBuiltin?.('temp')}
            onRename={() => onRequestRename?.('temp', t)}
            onAlert={() => onRequestAlert?.('temp', t)}
          >
            <BiChart type="line" series={temp.series} labels={temp.labels} unit=" °C" />
          </ChartCard>
        );
      })()}

      {isVisible('humidity') && (() => {
        const t = titleOf('humidity', 'Влажность воздуха');
        return (
          <ChartCard
            title={t}
            badges={[{ icon: '💧', label: 'По ферме' }]}
            legend={humidity.series}
            alertThreshold={alertThresholds['humidity']}
            onDelete={() => onRemoveBuiltin?.('humidity')}
            onRename={() => onRequestRename?.('humidity', t)}
            onAlert={() => onRequestAlert?.('humidity', t)}
          >
            <BiChart type="line" series={humidity.series} labels={humidity.labels} unit=" %" />
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
