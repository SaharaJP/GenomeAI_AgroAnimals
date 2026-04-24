'use client';

import dynamic from 'next/dynamic';
import { useState } from 'react';
import { DEMO_TIMELINE_EVENTS } from '@/lib/api/timeline';
import type { MetricWindow } from '@/lib/api/timeline';
import { EventList } from '@/components/timeline/event-list';
import { useAddEvent } from '@/components/app/add-event-context';

const ImpactPanel = dynamic(
  () => import('@/components/timeline/impact-panel').then((m) => m.ImpactPanel),
  {
    loading: () => (
      <div className="impact-empty">
        <div className="impact-empty-icon" style={{ background: 'none', opacity: 0.4 }}>⏳</div>
      </div>
    ),
    ssr: false,
  },
);

const DEFAULT_SELECTED = 'DEMO_001';

export default function TimelinePage() {
  const { openDialog, userEvents } = useAddEvent();

  const allEvents = [...userEvents, ...DEMO_TIMELINE_EVENTS];
  const eventIds = allEvents.map((e) => e.timeline_event_id);

  const [selectedId, setSelectedId] = useState<string | null>(DEFAULT_SELECTED);
  const [typeFilter, setTypeFilter] = useState('all');
  const [activeWindow, setActiveWindow] = useState<MetricWindow>('3d');
  const [swipeStartX, setSwipeStartX] = useState<number | null>(null);

  const selectedEvent = allEvents.find((e) => e.timeline_event_id === selectedId) ?? null;

  function navigateRelative(delta: 1 | -1) {
    const idx = selectedId ? eventIds.indexOf(selectedId) : -1;
    const next = eventIds[Math.max(0, Math.min(eventIds.length - 1, idx + delta))];
    if (next) {
      setSelectedId(next);
      setActiveWindow('3d');
    }
  }

  function handleTouchStart(e: React.TouchEvent) {
    setSwipeStartX(e.touches[0].clientX);
  }

  function handleTouchEnd(e: React.TouchEvent) {
    if (swipeStartX === null) return;
    const delta = swipeStartX - e.changedTouches[0].clientX;
    if (Math.abs(delta) > 60) navigateRelative(delta > 0 ? 1 : -1);
    setSwipeStartX(null);
  }

  return (
    <>
      <h1 className="page-title">Лента событий</h1>
      <p className="tl-page-subtitle">
        Хроника событий на ферме в хронологическом порядке, с оценкой их влияния.
      </p>

      <div
        className="tl-page"
        onTouchStart={handleTouchStart}
        onTouchEnd={handleTouchEnd}
      >
        <EventList
          events={allEvents}
          selectedId={selectedId}
          onSelect={(id) => {
            setSelectedId(id);
            setActiveWindow('3d');
          }}
          typeFilter={typeFilter}
          onTypeFilterChange={setTypeFilter}
          onAddEvent={openDialog}
        />

        <ImpactPanel
          event={selectedEvent}
          window={activeWindow}
          onWindowChange={setActiveWindow}
        />
      </div>
    </>
  );
}
