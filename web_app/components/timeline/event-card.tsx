import {
  Salad,
  UserPlus,
  Scissors,
  Users,
  Package,
  FlaskConical,
  ArrowRightLeft,
  Syringe,
  Heart,
  AlertCircle,
  TrendingUp,
  TrendingDown,
  ShieldCheck,
  Award,
  BarChart3,
  Clock,
  Trash2,
  Pencil,
} from 'lucide-react';
import type { TimelineEvent } from '@/lib/api/timeline';
import { formatDayMonth } from '@/lib/api/timeline';

const ICONS: Record<string, React.ReactNode> = {
  ration_change: <Salad size={15} />,
  new_employee: <UserPlus size={15} />,
  feeding_schedule: <Salad size={15} />,
  hoof_trim: <Scissors size={15} />,
  pen_density: <Users size={15} />,
  bedding: <Package size={15} />,
  mastitis_outbreak: <FlaskConical size={15} />,
  mastitis_recurrence: <FlaskConical size={15} />,
  pen_move: <ArrowRightLeft size={15} />,
  vaccination: <Syringe size={15} />,
  breeding: <Heart size={15} />,
  heat_detection: <Heart size={15} />,
  scc_alert: <AlertCircle size={15} />,
  scc_group_rise: <TrendingUp size={15} />,
  activity_drop: <TrendingDown size={15} />,
  withdrawal_compliance: <ShieldCheck size={15} />,
  benchmark_update: <Award size={15} />,
  daily_kpi_snapshot: <BarChart3 size={15} />,
};

type Props = {
  event: TimelineEvent;
  selected: boolean;
  onClick: () => void;
  onDelete?: (event: TimelineEvent) => void;
  onEdit?: (event: TimelineEvent) => void;
};

const isUserEvent = (e: TimelineEvent) =>
  e.timeline_event_id.startsWith('TL_') && e.source === 'Добавлено вручную';

export function EventCard({ event, selected, onClick, onDelete, onEdit }: Props) {
  const icon = ICONS[event.event_type] ?? <Clock size={15} />;
  const canMutate = isUserEvent(event);

  return (
    <div
      className={`timeline-event-item${selected ? ' timeline-event-item--selected' : ''}`}
      onClick={onClick}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') onClick(); }}
      aria-pressed={selected}
      style={{ position: 'relative' }}
    >
      <div className="timeline-event-icon">{icon}</div>
      <div className="timeline-event-body">
        <div className="timeline-event-title">{event.title}</div>
        <div className="timeline-event-desc">{event.body}</div>
        <div className="timeline-event-meta">
          <span className="timeline-event-date">{formatDayMonth(event.date)}</span>
          {event.has_impact && (
            <span className="badge badge-success" style={{ fontSize: 10, padding: '1px 6px' }}>
              ✓ Результаты готовы
            </span>
          )}
        </div>
      </div>
      {canMutate && (
        <div
          className="timeline-event-actions"
          style={{ display: 'flex', gap: 4, alignItems: 'center', flexShrink: 0 }}
          onClick={(e) => e.stopPropagation()}
        >
          {onEdit && (
            <button
              type="button"
              title="Редактировать"
              onClick={() => onEdit(event)}
              style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 4, color: 'var(--text-muted)' }}
            >
              <Pencil size={12} />
            </button>
          )}
          {onDelete && (
            <button
              type="button"
              title="Удалить"
              onClick={() => onDelete(event)}
              style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 4, color: 'var(--text-muted)' }}
            >
              <Trash2 size={12} />
            </button>
          )}
        </div>
      )}
    </div>
  );
}
