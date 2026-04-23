'use client';

import { useState } from 'react';
import { DEMO_TIMELINE_EVENTS } from '@/lib/api/timeline';
import type { MetricWindow } from '@/lib/api/timeline';
import { EventList } from '@/components/timeline/event-list';
import { ImpactPanel } from '@/components/timeline/impact-panel';

const DEFAULT_SELECTED = 'DEMO_001';

export default function TimelinePage() {
  const [selectedId, setSelectedId] = useState<string | null>(DEFAULT_SELECTED);
  const [typeFilter, setTypeFilter] = useState('all');
  const [activeWindow, setActiveWindow] = useState<MetricWindow>('3d');
  const [toastVisible, setToastVisible] = useState(false);

  const selectedEvent =
    DEMO_TIMELINE_EVENTS.find((e) => e.timeline_event_id === selectedId) ?? null;

  function handleAddEvent() {
    setToastVisible(true);
    setTimeout(() => setToastVisible(false), 3000);
  }

  return (
    <>
      <h1 className="page-title">Лента событий</h1>
      <p className="tl-page-subtitle">
        Хроника событий на ферме в хронологическом порядке, с оценкой их влияния.
      </p>

      <div className="tl-page">
        <EventList
          events={DEMO_TIMELINE_EVENTS}
          selectedId={selectedId}
          onSelect={(id) => {
            setSelectedId(id);
            setActiveWindow('3d');
          }}
          typeFilter={typeFilter}
          onTypeFilterChange={setTypeFilter}
          onAddEvent={handleAddEvent}
        />

        <ImpactPanel
          event={selectedEvent}
          window={activeWindow}
          onWindowChange={setActiveWindow}
        />
      </div>

      {toastVisible && (
        <div className="toast" role="status" aria-live="polite">
          Форма добавления события в разработке
        </div>
      )}
    </>
  );
}
