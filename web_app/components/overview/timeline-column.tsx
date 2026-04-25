'use client';

import { useState } from 'react';
import Link from 'next/link';
import { Clock, Plus, FlaskConical, UserPlus, ArrowRightLeft, Salad, Syringe, Heart } from 'lucide-react';
import { DEMO_TIMELINE_EVENTS, EVENT_TYPE_LABELS } from '@/lib/api/overview';
import type { OverviewTimelineEvent } from '@/lib/api/overview';
import { useAddEvent } from '@/components/app/add-event-context';

const EVENT_ICON: Record<string, React.ReactNode> = {
  mastitis_outbreak: <FlaskConical size={14} />,
  mastitis_recurrence: <FlaskConical size={14} />,
  pen_move: <ArrowRightLeft size={14} />,
  new_employee: <UserPlus size={14} />,
  feeding_schedule: <Salad size={14} />,
  ration_change: <Salad size={14} />,
  vaccination: <Syringe size={14} />,
  breeding: <Heart size={14} />,
};

function formatMonthYear(dateStr: string): string {
  const d = new Date(dateStr);
  return d.toLocaleDateString('ru-RU', { month: 'long', year: 'numeric' });
}

function formatDayMonthYear(dateStr: string): string {
  const d = new Date(dateStr);
  return d.toLocaleDateString('ru-RU', { day: 'numeric', month: 'long', year: 'numeric' });
}

function groupByMonth(events: OverviewTimelineEvent[]): Map<string, OverviewTimelineEvent[]> {
  const map = new Map<string, OverviewTimelineEvent[]>();
  for (const ev of events) {
    const key = formatMonthYear(ev.date);
    if (!map.has(key)) map.set(key, []);
    map.get(key)!.push(ev);
  }
  return map;
}

const ALL_TYPES = 'all';

export function TimelineColumn() {
  const [typeFilter, setTypeFilter] = useState(ALL_TYPES);
  const { openDialog } = useAddEvent();

  const uniqueTypes = Array.from(new Set(DEMO_TIMELINE_EVENTS.map(e => e.event_type)));

  const filtered = typeFilter === ALL_TYPES
    ? DEMO_TIMELINE_EVENTS
    : DEMO_TIMELINE_EVENTS.filter(e => e.event_type === typeFilter);

  const grouped = groupByMonth(filtered);

  return (
    <>
      <div className="col-card">
        <div className="col-header">
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <Clock size={15} color="var(--text-secondary)" />
            <span className="col-header-title">Лента событий</span>
          </div>
        </div>

        <div className="col-content">
          <div className="timeline-toolbar">
            <select
              className="timeline-select"
              value={typeFilter}
              onChange={(e: React.ChangeEvent<HTMLSelectElement>) => setTypeFilter(e.target.value)}
              aria-label="Тип события"
            >
              <option value={ALL_TYPES}>Все типы событий</option>
              {uniqueTypes.map(t => (
                <option key={t} value={t}>{EVENT_TYPE_LABELS[t] ?? t}</option>
              ))}
            </select>
            <button className="timeline-add-btn" onClick={openDialog}>
              <Plus size={12} />
              Добавить событие
            </button>
          </div>

          {filtered.length === 0 ? (
            <div className="empty-state" style={{ padding: '28px 0' }}>
              Нет событий выбранного типа.
            </div>
          ) : (
            Array.from(grouped.entries()).map(([month, events]) => (
              <div key={month} className="timeline-month-group">
                <div className="timeline-month-label">{month}</div>
                {events.map(ev => (
                  <Link
                    key={ev.timeline_event_id}
                    href="/timeline"
                    style={{ textDecoration: 'none', display: 'block' }}
                  >
                    <div className="timeline-event-item">
                      <div className="timeline-event-icon">
                        {EVENT_ICON[ev.event_type] ?? <Clock size={14} />}
                      </div>
                      <div className="timeline-event-body">
                        <div className="timeline-event-title">{ev.title}</div>
                        <div className="timeline-event-desc">{ev.body}</div>
                        <div className="timeline-event-meta">
                          <span className="timeline-event-date">{formatDayMonthYear(ev.date)}</span>
                          <span className="badge badge-success" style={{ fontSize: 10, padding: '1px 6px' }}>
                            Результаты готовы
                          </span>
                        </div>
                      </div>
                    </div>
                  </Link>
                ))}
              </div>
            ))
          )}
        </div>

        <div className="col-footer">
          <Link href="/timeline" style={{ fontSize: 12, color: 'var(--accent-text)', fontWeight: 500 }}>
            Полная лента событий →
          </Link>
        </div>
      </div>

    </>
  );
}
