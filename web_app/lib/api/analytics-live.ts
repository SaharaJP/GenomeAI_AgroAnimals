'use client';
import { useEffect, useState } from 'react';
import type { AnalyticsData } from './analytics';

export interface TabTimeseries {
  tab: string;
  labels: string[];
  iso_dates?: string[];
  charts: Record<string, AnalyticsData>;
}

type LoadState = { status: 'loading' } | { status: 'ok'; data: TabTimeseries } | { status: 'error' };

export function useAnalyticsTimeseries(tab: string, weeks = 26): LoadState {
  const [state, setState] = useState<LoadState>({ status: 'loading' });

  useEffect(() => {
    let active = true;
    setState({ status: 'loading' });

    fetch(`/api/analytics/timeseries/${tab}?weeks=${weeks}`)
      .then(async (res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json() as Promise<TabTimeseries>;
      })
      .then((data) => {
        if (active) setState({ status: 'ok', data });
      })
      .catch(() => {
        if (active) setState({ status: 'error' });
      });

    return () => { active = false; };
  }, [tab, weeks]);

  return state;
}

/** Placeholder chart data shown while loading or on error. */
export function emptyChart(name: string, color = '#94A3B8'): AnalyticsData {
  return { labels: [], series: [{ name, color, data: [] }] };
}
