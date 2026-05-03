'use client';

import dynamic from 'next/dynamic';
import { useState, useEffect, useCallback, useRef } from 'react';
import { DEMO_TIMELINE_EVENTS } from '@/lib/api/timeline';
import type { MetricWindow, TimelineEvent } from '@/lib/api/timeline';
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

function dedup(events: TimelineEvent[]): TimelineEvent[] {
  const seen = new Set<string>();
  return events.filter((e) => {
    if (seen.has(e.timeline_event_id)) return false;
    seen.add(e.timeline_event_id);
    return true;
  });
}

export default function TimelinePage() {
  const { openDialog, userEvents } = useAddEvent();

  const [dbEvents, setDbEvents] = useState<TimelineEvent[]>([]);
  const prevUserEventsLen = useRef(0);

  const fetchDbEvents = useCallback(async () => {
    try {
      const res = await fetch('/api/backend/api/timeline/events', { cache: 'no-store' });
      if (!res.ok) return;
      const data = await res.json();
      // Берём только user-события из БД (не DEMO_ из локального ts-файла)
      const events: TimelineEvent[] = (data.events ?? []).filter(
        (e: TimelineEvent) => !e.timeline_event_id.startsWith('DEMO_'),
      );
      setDbEvents(events);
    } catch {
      // сеть недоступна — молча показываем демо
    }
  }, []);

  // Загружаем из БД при монтировании
  useEffect(() => { fetchDbEvents(); }, [fetchDbEvents]);

  // Рефетчим из БД после оптимистичного добавления через контекст
  useEffect(() => {
    if (userEvents.length > prevUserEventsLen.current) {
      prevUserEventsLen.current = userEvents.length;
      const t = setTimeout(() => fetchDbEvents(), 400);
      return () => clearTimeout(t);
    }
    prevUserEventsLen.current = userEvents.length;
  }, [userEvents.length, fetchDbEvents]);

  // Объединяем: оптимистичные → БД → демо-события с impact-анализом
  const allEvents = dedup([...userEvents, ...dbEvents, ...DEMO_TIMELINE_EVENTS]);
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
