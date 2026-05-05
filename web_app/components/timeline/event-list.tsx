import { Plus } from 'lucide-react';
import type { TimelineEvent } from '@/lib/api/timeline';
import { EVENT_TYPE_LABELS, groupEventsByMonth } from '@/lib/api/timeline';
import { EventCard } from './event-card';

type Props = {
  events: TimelineEvent[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  typeFilter: string;
  onTypeFilterChange: (t: string) => void;
  onAddEvent: () => void;
  onDeleteEvent?: (event: TimelineEvent) => void;
  onEditEvent?: (event: TimelineEvent) => void;
};

export function EventList({
  events,
  selectedId,
  onSelect,
  typeFilter,
  onTypeFilterChange,
  onAddEvent,
  onDeleteEvent,
  onEditEvent,
}: Props) {
  const uniqueTypes = Array.from(new Set(events.map((e) => e.event_type)));

  const filtered =
    typeFilter === 'all' ? events : events.filter((e) => e.event_type === typeFilter);

  const grouped = groupEventsByMonth(filtered);

  return (
    <div className="tl-left">
      <div className="tl-left-header">
        <select
          className="timeline-select"
          value={typeFilter}
          onChange={(e: React.ChangeEvent<HTMLSelectElement>) => onTypeFilterChange(e.target.value)}
          aria-label="Тип события"
        >
          <option value="all">Все типы событий</option>
          {uniqueTypes.map((t) => (
            <option key={t} value={t}>
              {EVENT_TYPE_LABELS[t] ?? t}
            </option>
          ))}
        </select>
        <button className="timeline-add-btn" onClick={onAddEvent} type="button">
          <Plus size={12} />
          Добавить событие
        </button>
      </div>

      <div className="tl-left-body">
        {filtered.length === 0 ? (
          <div className="empty-state" style={{ padding: '28px 0' }}>
            Нет событий выбранного типа.
          </div>
        ) : (
          Array.from(grouped.entries()).map(([month, monthEvents]) => (
            <div key={month} className="timeline-month-group">
              <div className="timeline-month-label">{month}</div>
              {monthEvents.map((ev) => (
                <EventCard
                  key={ev.timeline_event_id}
                  event={ev}
                  selected={selectedId === ev.timeline_event_id}
                  onClick={() => onSelect(ev.timeline_event_id)}
                  onDelete={onDeleteEvent}
                  onEdit={onEditEvent}
                />
              ))}
            </div>
          ))
        )}
      </div>
    </div>
  );
}
