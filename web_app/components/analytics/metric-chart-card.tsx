'use client';
import {
  getProductionMilkEcm,
  getProductionFatProtein,
  getProductionScc,
  getReproductionRates,
  getReproductionDaysOpen,
  getReproductionVwp,
  getReproductionVwpYoungstock,
  getFeedDmi,
  getFeedCost,
  getFeedEfficiency,
  getBehaviorRumination,
  getBehaviorActivity,
  getBehaviorLying,
  getHerdSize,
  getHerdDimDistribution,
  getHerdCalvings,
  getWeatherThi,
  getWeatherTemp,
  getWeatherHumidity,
  getFinanceRevenue,
  getFinanceFeedCost,
  getFinanceMargin,
  getHealthMastitis,
  getHealthIssues,
} from '@/lib/api/analytics';
import type { AnalyticsData } from '@/lib/api/analytics';
import { ChartCard } from './chart-card';
import { BiChart } from './bi-chart';
import { METRICS } from './add-chart-dialog';
import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { useOverlays } from './analytics-overlays-context';
import { QcIncidentCard } from './qc-incident-card';
import { FullscreenChartModal } from './fullscreen-chart-modal';
import type { QcIncident } from '@/lib/api/qc-client';

interface Spec {
  data: () => AnalyticsData;
  unit: string;
  refLine?: number;
}

const SPECS: Record<string, Spec> = {
  milk_ecm:         { data: getProductionMilkEcm,        unit: ' кг'  },
  fat_protein:      { data: getProductionFatProtein,     unit: '%'    },
  scc:              { data: getProductionScc,            unit: 'k', refLine: 200 },
  fat_per_cow:      { data: getProductionFatProtein,     unit: '%'    },
  protein_per_cow:  { data: getProductionFatProtein,     unit: '%'    },
  milk_per_cow:     { data: getProductionMilkEcm,        unit: ' кг'  },
  milk_visits:      { data: getBehaviorActivity,         unit: ''     },

  dmi:              { data: getFeedDmi,                  unit: ' кг'  },
  feed_cost:        { data: getFeedCost,                 unit: ' р'   },
  feed_efficiency:  { data: getFeedEfficiency,           unit: ''     },

  repro_rates:      { data: getReproductionRates,        unit: '%'    },
  days_open:        { data: getReproductionDaysOpen,     unit: ' дн'  },
  calving_interval: { data: getReproductionVwp,          unit: ' дн'  },
  vwp:              { data: getReproductionVwpYoungstock,unit: ' дн'  },

  mastitis:         { data: getHealthMastitis,           unit: ' гол' },
  health_issues:    { data: getHealthIssues,             unit: ' гол' },
  culling_rate:     { data: getHealthMastitis,           unit: '%'    },
  treatment_count:  { data: getHealthIssues,             unit: ' гол' },

  rumination:       { data: getBehaviorRumination,       unit: ' мин' },
  activity:         { data: getBehaviorActivity,         unit: ''     },

  herd_size:        { data: getHerdSize,                 unit: ' гол' },
  dim_distribution: { data: getHerdDimDistribution,      unit: ' гол' },
};

interface Props {
  metricId: string;
  titleOverride?: string;
  alertThreshold?: string;
  onDelete?: () => void;
  onRename?: (key: string, currentTitle: string) => void;
  onAlert?: (key: string, currentTitle: string) => void;
}

export function MetricChartCard({ metricId, titleOverride, alertThreshold, onDelete, onRename, onAlert }: Props) {
  const meta = METRICS.find((m) => m.id === metricId);
  const spec = SPECS[metricId];
  const title = titleOverride ?? meta?.name ?? metricId;

  // Fallback: unknown metric id
  if (!spec) {
    return (
      <ChartCard
        title={title}
        badges={meta ? [{ icon: '📊', label: meta.group }] : []}
        alertThreshold={alertThreshold}
        onDelete={onDelete}
        onRename={onRename ? () => onRename(metricId, title) : undefined}
        onAlert={onAlert ? () => onAlert(metricId, title) : undefined}
      >
        <div style={{ height: 140, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-muted)', fontSize: 12 }}>
          {meta?.desc ?? 'Данные накапливаются…'}
        </div>
      </ChartCard>
    );
  }

  const overlays = useOverlays();
  const router = useRouter();
  const [openIncident, setOpenIncident] = useState<QcIncident | null>(null);
  const [fullscreen, setFullscreen] = useState(false);
  const chart = spec.data();

  const qcOverlays = overlays.showQc ? (overlays.qcByMetric[metricId] ?? []).map((inc) => {
    const startIso = inc.period_start.slice(0, 10);
    const endIso = inc.period_end?.slice(0, 10) ?? null;
    const startIdx = chart.labels.indexOf(startIso);
    const endIdx = endIso ? chart.labels.indexOf(endIso) : null;
    return {
      incident_id: inc.incident_id,
      period_start_idx: startIdx >= 0 ? startIdx : 0,
      period_end_idx: endIdx === null ? null : (endIdx >= 0 ? endIdx : chart.labels.length - 1),
      severity: inc.severity,
      root_cause: inc.root_cause,
      ai_description: inc.ai_description,
    };
  }) : [];

  const eventMarkers = overlays.showEvents ? (overlays.eventsByMetric[metricId] ?? []).map((ev) => ({
    event_id: ev.event_id,
    date_idx: chart.labels.indexOf(ev.event_date.slice(0, 10)),
    title: ev.title,
    event_date: ev.event_date,
  })).filter((m) => m.date_idx >= 0) : [];

  function onQcClick(incident_id: string) {
    const inc = (overlays.qcByMetric[metricId] ?? []).find((i) => i.incident_id === incident_id);
    if (inc) setOpenIncident(inc);
  }
  function onEventClick(event_id: string) {
    router.push(`/timeline?event=${encodeURIComponent(event_id)}`);
  }

  return (
    <>
      <ChartCard
        title={title}
        badges={meta ? [{ icon: '📊', label: meta.group }] : []}
        legend={chart.series}
        alertThreshold={alertThreshold}
        onDelete={onDelete}
        onRename={onRename ? () => onRename(metricId, title) : undefined}
        onAlert={onAlert ? () => onAlert(metricId, title) : undefined}
        onMaximize={() => setFullscreen(true)}
      >
        <BiChart
          type="line"
          series={chart.series}
          labels={chart.labels}
          unit={spec.unit}
          refLine={spec.refLine}
          qcOverlays={qcOverlays}
          eventMarkers={eventMarkers}
          onQcClick={onQcClick}
          onEventClick={onEventClick}
        />
      </ChartCard>
      {openIncident && (
        <QcIncidentCard
          incident={openIncident}
          onClose={() => setOpenIncident(null)}
          onDismissed={() => { setOpenIncident(null); overlays.refetch(); }}
        />
      )}
      <FullscreenChartModal
        open={fullscreen}
        title={title}
        onClose={() => setFullscreen(false)}
      >
        <BiChart
          type="line"
          series={chart.series}
          labels={chart.labels}
          unit={spec.unit}
          refLine={spec.refLine}
          qcOverlays={qcOverlays}
          eventMarkers={eventMarkers}
          onQcClick={onQcClick}
          onEventClick={onEventClick}
        />
      </FullscreenChartModal>
    </>
  );
}
