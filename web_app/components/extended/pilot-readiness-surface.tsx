'use client';
import { useEffect, useState } from 'react';
import { Card, MetricCard } from '@/components/ui/card';
import { fetchExtendedBundle } from '@/lib/api/extended-surfaces';
import type { PilotResponse, ReadinessResponse } from '@/lib/api/contracts';

export function PilotSurface() {
  const [payload, setPayload] = useState<PilotResponse | null>(null);
  useEffect(() => { let active = true; void fetchExtendedBundle().then((bundle) => { if (active) setPayload(bundle.pilot); }); return () => { active = false; }; }, []);
  return <div className="grid">{!payload ? <div className="card">Loading pilot surface…</div> : <>
    <div className="grid grid-3">
      <MetricCard title="Pilot packs" value={payload.summary.total_pilot_packs} />
      <MetricCard title="Latest data version" value={payload.summary.latest_data_version || '—'} />
      <MetricCard title="Latest pack" value={payload.summary.latest_pack_id || '—'} />
    </div>
    <Card><h3 className="card-title">Pilot evidence</h3><pre style={{ whiteSpace: 'pre-wrap', marginTop: 12 }}>{JSON.stringify(payload, null, 2)}</pre></Card>
  </>}</div>;
}

export function ReadinessSurface() {
  const [payload, setPayload] = useState<ReadinessResponse | null>(null);
  useEffect(() => { let active = true; void fetchExtendedBundle().then((bundle) => { if (active) setPayload(bundle.readiness); }); return () => { active = false; }; }, []);
  return <div className="grid">{!payload ? <div className="card">Loading readiness surface…</div> : <>
    <div className="grid grid-3">
      <MetricCard title="Overall status" value={payload.summary.overall_status} />
      <MetricCard title="Checks total" value={payload.summary.checks_total} />
      <MetricCard title="Warnings / failed" value={`${payload.summary.warnings} / ${payload.summary.failed}`} />
    </div>
    <Card><h3 className="card-title">Readiness checks</h3><pre style={{ whiteSpace: 'pre-wrap', marginTop: 12 }}>{JSON.stringify(payload, null, 2)}</pre></Card>
  </>}</div>;
}
