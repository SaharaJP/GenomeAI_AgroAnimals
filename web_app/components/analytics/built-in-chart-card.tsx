'use client';
import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { ChartCard } from './chart-card';
import { BiChart } from './bi-chart';
import { useOverlays } from './analytics-overlays-context';
import { QcIncidentCard } from './qc-incident-card';
import { FullscreenChartModal } from './fullscreen-chart-modal';
import type { QcIncident } from '@/lib/api/qc-client';
import type { ChartSeries } from '@/lib/api/analytics';
import { findChartIndex } from '@/lib/api/analytics';

interface Badge { icon: string; label: string }

interface Props {
  metricId: string;
  title: string;
  badges?: Badge[];
  legend?: ChartSeries[];
  series: ChartSeries[];
  labels: string[];
  /** ISO Monday dates parallel to `labels` — overlays use this to align by date. */
  isoDates?: string[];
  unit?: string;
  refLine?: number;
  alertThreshold?: string;
  onAlert?: () => void;
  onDelete?: () => void;
  onRename?: () => void;
}

export function BuiltInChartCard({
  metricId, title, badges, legend, series, labels, isoDates, unit, refLine,
  alertThreshold, onAlert, onDelete, onRename,
}: Props) {
  const overlays = useOverlays();
  const router = useRouter();
  const [openIncident, setOpenIncident] = useState<QcIncident | null>(null);
  const [fullscreen, setFullscreen] = useState(false);

  // Overlays align against the chart's own iso_dates (parallel to labels).
  // Fallback empty array → all findChartIndex calls return -1 → overlays hidden.
  const chartIso = isoDates ?? [];

  const qcOverlays = overlays.showQc
    ? (overlays.qcByMetric[metricId] ?? []).flatMap((inc) => {
        const startIso = inc.period_start.slice(0, 10);
        const endIso = inc.period_end?.slice(0, 10) ?? null;
        const startIdx = findChartIndex(chartIso, startIso);
        const endIdx = endIso ? findChartIndex(chartIso, endIso) : null;
        // Skip if entire range is outside chart's visible date range
        if (startIdx < 0 && (endIdx === null || endIdx < 0)) return [];
        return [{
          incident_id: inc.incident_id,
          period_start_idx: startIdx >= 0 ? startIdx : 0,
          period_end_idx: endIdx === null ? null : (endIdx >= 0 ? endIdx : labels.length - 1),
          severity: inc.severity,
          root_cause: inc.root_cause,
          ai_description: inc.ai_description,
        }];
      })
    : [];

  const eventMarkers = overlays.showEvents
    ? (overlays.eventsByMetric[metricId] ?? []).map((ev) => ({
        event_id: ev.event_id,
        date_idx: findChartIndex(chartIso, ev.event_date.slice(0, 10)),
        title: ev.title,
        event_date: ev.event_date,
      })).filter((m) => m.date_idx >= 0)
    : [];

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
        badges={badges}
        legend={legend}
        alertThreshold={alertThreshold}
        onAlert={onAlert}
        onDelete={onDelete}
        onRename={onRename}
        onMaximize={() => setFullscreen(true)}
      >
        <BiChart
          type="line"
          series={series}
          labels={labels}
          unit={unit}
          refLine={refLine}
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
          series={series}
          labels={labels}
          unit={unit}
          refLine={refLine}
          qcOverlays={qcOverlays}
          eventMarkers={eventMarkers}
          onQcClick={onQcClick}
          onEventClick={onEventClick}
        />
      </FullscreenChartModal>
    </>
  );
}
