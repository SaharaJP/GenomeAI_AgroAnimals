'use client';
import { getWeatherThi, getWeatherTemp, getWeatherHumidity, WEEK_ISO_DATES } from '@/lib/api/analytics';
import { EmptyChartSlot } from './empty-chart-slot';
import { MetricChartCard } from './metric-chart-card';
import { BuiltInChartCard } from './built-in-chart-card';

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
          <BuiltInChartCard
            metricId="thi"
            title={t}
            badges={[{ icon: '🌡️', label: 'По ферме' }, { icon: '⚠️', label: 'Порог: 72' }]}
            legend={thi.series}
            series={thi.series}
            labels={thi.labels}
            isoDates={WEEK_ISO_DATES}
            unit=""
            refLine={72}
            alertThreshold={alertThresholds['thi']}
            onDelete={() => onRemoveBuiltin?.('thi')}
            onRename={() => onRequestRename?.('thi', t)}
            onAlert={() => onRequestAlert?.('thi', t)}
          />
        );
      })()}

      {isVisible('temp') && (() => {
        const t = titleOf('temp', 'Температура воздуха');
        return (
          <BuiltInChartCard
            metricId="temp"
            title={t}
            badges={[{ icon: '🌡️', label: 'По ферме' }]}
            legend={temp.series}
            series={temp.series}
            labels={temp.labels}
            isoDates={WEEK_ISO_DATES}
            unit=" °C"
            alertThreshold={alertThresholds['temp']}
            onDelete={() => onRemoveBuiltin?.('temp')}
            onRename={() => onRequestRename?.('temp', t)}
            onAlert={() => onRequestAlert?.('temp', t)}
          />
        );
      })()}

      {isVisible('humidity') && (() => {
        const t = titleOf('humidity', 'Влажность воздуха');
        return (
          <BuiltInChartCard
            metricId="humidity"
            title={t}
            badges={[{ icon: '💧', label: 'По ферме' }]}
            legend={humidity.series}
            series={humidity.series}
            labels={humidity.labels}
            isoDates={WEEK_ISO_DATES}
            unit=" %"
            alertThreshold={alertThresholds['humidity']}
            onDelete={() => onRemoveBuiltin?.('humidity')}
            onRename={() => onRequestRename?.('humidity', t)}
            onAlert={() => onRequestAlert?.('humidity', t)}
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
