import { getWeatherThi, getWeatherTemp, getWeatherHumidity } from '@/lib/api/analytics';
import { ChartCard } from './chart-card';
import { BiChart } from './bi-chart';
import { EmptyChartSlot } from './empty-chart-slot';
import { METRICS } from './add-chart-dialog';

const thi      = getWeatherThi();
const temp     = getWeatherTemp();
const humidity = getWeatherHumidity();

interface Props {
  onAddChart: () => void;
  addedMetricIds?: string[];
  onRemoveChart?: (id: string) => void;
}

export function WeatherTab({ onAddChart, addedMetricIds = [], onRemoveChart }: Props) {
  return (
    <div className="grid grid-2">
      <ChartCard
        title="Индекс тепловой нагрузки (ТГИ)"
        badges={[{ icon: '🌡️', label: 'По ферме' }, { icon: '⚠️', label: 'Порог: 72' }]}
        legend={thi.series}
      >
        <BiChart type="line" series={thi.series} labels={thi.labels} unit="" refLine={72} />
      </ChartCard>

      <ChartCard
        title="Температура воздуха"
        badges={[{ icon: '🌡️', label: 'По ферме' }]}
        legend={temp.series}
      >
        <BiChart type="line" series={temp.series} labels={temp.labels} unit=" °C" />
      </ChartCard>

      <ChartCard
        title="Влажность воздуха"
        badges={[{ icon: '💧', label: 'По ферме' }]}
        legend={humidity.series}
      >
        <BiChart type="line" series={humidity.series} labels={humidity.labels} unit=" %" />
      </ChartCard>

      {addedMetricIds.map(id => {
        const metric = METRICS.find(m => m.id === id);
        return (
          <ChartCard
            key={id}
            title={metric?.name ?? id}
            badges={metric ? [{ icon: '📊', label: metric.group }] : []}
            onDelete={() => onRemoveChart?.(id)}
          >
            <div style={{ height: 140, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-muted)', fontSize: 12 }}>
              {metric?.desc ?? 'Данные загружаются…'}
            </div>
          </ChartCard>
        );
      })}

      <EmptyChartSlot onAdd={onAddChart} />
    </div>
  );
}
