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
};

export function EventCard({ event, selected, onClick }: Props) {
  const icon = ICONS[event.event_type] ?? <Clock size={15} />;

  return (
    <div
      className={`timeline-event-item${selected ? ' timeline-event-item--selected' : ''}`}
      onClick={onClick}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') onClick(); }}
      aria-pressed={selected}
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
    </div>
  );
}
