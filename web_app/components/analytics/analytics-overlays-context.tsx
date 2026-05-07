'use client';
import { createContext, useContext, useEffect, useState, useMemo, useCallback, type ReactNode } from 'react';
import { fetchQcIncidents, type QcIncident } from '@/lib/api/qc-client';

export interface OverlayEvent {
  event_id: string;
  title: string;
  event_date: string;
  linked_metric_ids: string[];
}

interface OverlaysCtx {
  showQc: boolean;
  showEvents: boolean;
  setShowQc: (v: boolean) => void;
  setShowEvents: (v: boolean) => void;
  qcByMetric: Record<string, QcIncident[]>;
  eventsByMetric: Record<string, OverlayEvent[]>;
  refetch: () => Promise<void>;
}

const Ctx = createContext<OverlaysCtx | null>(null);

const LS_QC = 'analytics.show_qc';
const LS_EV = 'analytics.show_events';

function readLs(key: string, dflt: boolean): boolean {
  if (typeof window === 'undefined') return dflt;
  const v = window.localStorage.getItem(key);
  return v === null ? dflt : v === 'true';
}

export function AnalyticsOverlaysProvider({ farmId, children }: { farmId: string; children: ReactNode }) {
  const [showQc, _setShowQc] = useState<boolean>(() => readLs(LS_QC, true));
  const [showEvents, _setShowEvents] = useState<boolean>(() => readLs(LS_EV, true));
  const [qcByMetric, setQcByMetric] = useState<Record<string, QcIncident[]>>({});
  const [eventsByMetric, setEventsByMetric] = useState<Record<string, OverlayEvent[]>>({});

  const setShowQc = useCallback((v: boolean) => {
    _setShowQc(v);
    if (typeof window !== 'undefined') window.localStorage.setItem(LS_QC, String(v));
  }, []);
  const setShowEvents = useCallback((v: boolean) => {
    _setShowEvents(v);
    if (typeof window !== 'undefined') window.localStorage.setItem(LS_EV, String(v));
  }, []);

  const refetch = useCallback(async () => {
    try {
      const qc = await fetchQcIncidents({ farmId, active: true });
      const grouped: Record<string, QcIncident[]> = {};
      for (const inc of qc.items) {
        (grouped[inc.metric_id] ||= []).push(inc);
      }
      setQcByMetric(grouped);
    } catch {
      setQcByMetric({});
    }
    try {
      const r = await fetch(`/api/backend/api/timeline/events?farm_id=${encodeURIComponent(farmId)}`, { cache: 'no-store' });
      if (r.ok) {
        const data = await r.json();
        const items: OverlayEvent[] = (data.items || []).map((e: { event_id?: string; timeline_event_id?: string; title?: string; event_date?: string; date?: string; linked_metric_ids?: string[] }) => ({
          event_id: e.event_id ?? e.timeline_event_id ?? '',
          title: e.title ?? '',
          event_date: e.event_date ?? e.date ?? '',
          linked_metric_ids: e.linked_metric_ids ?? [],
        }));
        const grouped: Record<string, OverlayEvent[]> = {};
        for (const ev of items) {
          for (const m of ev.linked_metric_ids) {
            (grouped[m] ||= []).push(ev);
          }
        }
        setEventsByMetric(grouped);
      } else {
        setEventsByMetric({});
      }
    } catch {
      setEventsByMetric({});
    }
  }, [farmId]);

  useEffect(() => { refetch(); }, [refetch]);

  const value = useMemo<OverlaysCtx>(() => ({
    showQc, showEvents, setShowQc, setShowEvents,
    qcByMetric, eventsByMetric, refetch,
  }), [showQc, showEvents, setShowQc, setShowEvents, qcByMetric, eventsByMetric, refetch]);

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useOverlays(): OverlaysCtx {
  const v = useContext(Ctx);
  if (!v) throw new Error('useOverlays must be used inside AnalyticsOverlaysProvider');
  return v;
}
