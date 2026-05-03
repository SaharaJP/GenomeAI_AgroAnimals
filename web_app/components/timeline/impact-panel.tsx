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
  MousePointerClick,
  Plus,
  Cpu,
} from 'lucide-react';
import type { TimelineEvent, MetricWindow } from '@/lib/api/timeline';
import { getImpactForEvent, formatDayMonth, formatRelativeDate } from '@/lib/api/timeline';
import { WindowTabs } from './window-tabs';
import { MetricCompareCard } from './metric-compare-card';
import { OtherChangesTable } from './other-changes-table';

const ICONS: Record<string, React.ReactNode> = {
  ration_change: <Salad size={18} />,
  new_employee: <UserPlus size={18} />,
  feeding_schedule: <Salad size={18} />,
  hoof_trim: <Scissors size={18} />,
  pen_density: <Users size={18} />,
  bedding: <Package size={18} />,
  mastitis_outbreak: <FlaskConical size={18} />,
  mastitis_recurrence: <FlaskConical size={18} />,
  pen_move: <ArrowRightLeft size={18} />,
  vaccination: <Syringe size={18} />,
  breeding: <Heart size={18} />,
  heat_detection: <Heart size={18} />,
  scc_alert: <AlertCircle size={18} />,
  scc_group_rise: <TrendingUp size={18} />,
  activity_drop: <TrendingDown size={18} />,
  withdrawal_compliance: <ShieldCheck size={18} />,
  benchmark_update: <Award size={18} />,
  daily_kpi_snapshot: <BarChart3 size={18} />,
};

type Props = {
  event: TimelineEvent | null;
  window: MetricWindow;
  onWindowChange: (w: MetricWindow) => void;
};

export function ImpactPanel({ event, window: activeWindow, onWindowChange }: Props) {
  if (!event) {
    return (
      <div className="tl-right">
        <div className="impact-empty">
          <div className="impact-empty-icon">
            <MousePointerClick size={22} />
          </div>
          <div className="impact-empty-title">Выберите событие</div>
          <div className="impact-empty-sub">
            Кликните на событие слева, чтобы увидеть анализ его влияния на метрики фермы.
          </div>
        </div>
      </div>
    );
  }

  const icon = ICONS[event.event_type] ?? <Clock size={18} />;
  const impact = getImpactForEvent(event.timeline_event_id, activeWindow);

  return (
    <div className="tl-right">
      {/* Header */}
      <div className="impact-panel-header">
        <div className="impact-panel-event-row">
          <div className="impact-panel-event-icon">{icon}</div>
          <div style={{ flex: 1 }}>
            <div className="impact-panel-event-title">{event.title}</div>
            <div className="impact-panel-event-meta">
              <span>{formatDayMonth(event.date)}</span>
              <span style={{ color: 'var(--border-strong)' }}>·</span>
              <span>{formatRelativeDate(event.date)}</span>
            </div>
            {event.source && (
              <div className="impact-panel-source">
                <Cpu size={11} />
                {event.source}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Body */}
      <div className="impact-panel-body">
        {/* Section title */}
        <div className="impact-section-title">
          <span className="impact-section-heading">Потенциально затронутые метрики</span>
          <span className="impact-beta-badge">Beta</span>
        </div>

        <p className="impact-explain-text">
          Оцените KPI ДО и ПОСЛЕ изменения, чтобы понять его влияние. Используйте переключатель
          диапазона, чтобы увидеть значения ключевых метрик в разных временных окнах.
        </p>

        {impact ? (
          <>
            {/* Period labels */}
            <div className="impact-period-row">
              <span className="impact-period-label">До:</span>
              <span className="impact-period-value">
                {impact.before_period.start} — {impact.before_period.end}
              </span>
              <span className="impact-period-label" style={{ marginLeft: 8 }}>После:</span>
              <span className="impact-period-value">
                {impact.after_period.start} — {impact.after_period.end}
              </span>
            </div>

            {/* Window tabs */}
            <WindowTabs active={activeWindow} onChange={onWindowChange} />

            {/* Metrics grid */}
            <div className="impact-metrics-grid">
              {impact.metrics.map((m) => (
                <MetricCompareCard key={m.metric_id} metric={m} />
              ))}
            </div>

            {/* Add chart */}
            <div className="impact-add-chart-row">
              <select className="impact-add-chart-select" defaultValue="">
                <option value="" disabled>Выберите метрику...</option>
                <option>Lying time per cow, per day</option>
                <option>Steps per cow, per day</option>
                <option>SCC individual</option>
                <option>Body condition score</option>
                <option>Feed push frequency</option>
              </select>
              <button className="impact-add-chart-btn" type="button">
                <Plus size={12} />
                Добавить
              </button>
            </div>

            {/* Other changes */}
            {impact.other_changes.length > 0 && (
              <div className="impact-other-section">
                <div className="impact-other-title">Что ещё случилось?</div>
                <div className="impact-other-subtitle">
                  Другие изменения в метриках, которые могут быть связаны с этим событием
                </div>
                <OtherChangesTable changes={impact.other_changes} />
              </div>
            )}
          </>
        ) : (
          <div className="empty-state" style={{ padding: '32px 0', textAlign: 'center' }}>
            <div style={{ marginBottom: 8, color: 'var(--text-muted)', fontSize: 13 }}>
              Данные анализа ещё не готовы
            </div>
            <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>
              Impact analysis появится автоматически после накопления достаточного количества данных
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
