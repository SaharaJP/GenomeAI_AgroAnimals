'use client';

import { useState, useEffect } from 'react';
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
  Loader2,
  HelpCircle,
  X,
} from 'lucide-react';
import type { TimelineEvent, MetricWindow, ImpactWindowData } from '@/lib/api/timeline';
import { fetchImpactForEvent, formatDayMonth, formatRelativeDate } from '@/lib/api/timeline';
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
  const [impact, setImpact] = useState<ImpactWindowData | null>(null);
  const [loading, setLoading] = useState(false);
  const [fetchError, setFetchError] = useState(false);
  const [addToast, setAddToast] = useState('');
  const [selectedMetric, setSelectedMetric] = useState('');
  const [customMetrics, setCustomMetrics] = useState<string[]>([]);

  function handleAddMetric() {
    if (!selectedMetric) {
      setAddToast('Выберите метрику из списка');
      setTimeout(() => setAddToast(''), 2500);
      return;
    }
    if (customMetrics.includes(selectedMetric)) {
      setAddToast('Эта метрика уже добавлена');
      setTimeout(() => setAddToast(''), 2500);
      return;
    }
    setCustomMetrics((prev) => [...prev, selectedMetric]);
    setSelectedMetric('');
    setAddToast('Метрика добавлена — данные появятся после накопления статистики');
    setTimeout(() => setAddToast(''), 3500);
  }

  function handleDownloadHelp() {
    const text = `GenomeAI AgroAnimals — Методология анализа влияния событий
================================================================

ПРИНЦИП РАБОТЫ
Лента событий сопоставляет управленческие решения с динамикой ключевых метрик стада.
Для каждого события система формирует "до" и "после" на основе выбранного временного окна.

ВРЕМЕННЫЕ ОКНА
• 1 день (1d)  — сравнивает 1 день до и 1 день после события
• 3 дня (3d)  — сравнивает 3 дня до и 3 дня после
• 7 дней (7d)  — сравнивает 7 дней до и 7 дней после
• 14 дней (14d) — сравнивает 14 дней до и 14 дней после

АНАЛИЗИРУЕМЫЕ МЕТРИКИ
• Надой (кг/голову/день) — основная производственная метрика
• Жир (%) — качественный показатель молока
• Белок (%) — качественный показатель молока
• SCC (тыс/мл) — соматические клетки, индикатор здоровья вымени
• Активность (шагов/сутки) — поведенческая метрика

РАСЧЁТ ИЗМЕНЕНИЯ
Δ = (среднее "после") − (среднее "до")
Δ% = Δ / среднее "до" × 100%

Зелёный цвет = улучшение показателя относительно исходного значения.
Красный цвет = ухудшение показателя.

ПОЛЬЗОВАТЕЛЬСКИЕ СОБЫТИЯ
Добавленные вручную события помечаются источником "Добавлено вручную".
Только пользовательские события можно редактировать и удалять.
Демонстрационные события (DEMO_) используются для калибровки отображения.

ВАЖНО
• Анализ влияния носит информационный характер и не заменяет ветеринарное заключение.
• Для достоверных результатов рекомендуется окно ≥ 7 дней.
• Корреляция не означает причинно-следственную связь.

GenomeAI AgroAnimals © ${new Date().getFullYear()}
`;
    const blob = new Blob([text], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'genomeai-timeline-math.txt';
    a.click();
    URL.revokeObjectURL(url);
  }

  useEffect(() => {
    if (!event) {
      setImpact(null);
      setFetchError(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setFetchError(false);
    fetchImpactForEvent(event, activeWindow).then((data) => {
      if (!cancelled) {
        setImpact(data);
        setFetchError(data === null);
        setLoading(false);
      }
    });
    return () => { cancelled = true; };
  }, [event?.timeline_event_id, activeWindow]);

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

  return (
    <>
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
          <button
            type="button"
            onClick={handleDownloadHelp}
            title="Скачать описание математики"
            style={{
              background: 'none', border: 'none', cursor: 'pointer',
              color: 'var(--text-muted)', padding: 4, flexShrink: 0,
              display: 'inline-flex', alignItems: 'center',
            }}
          >
            <HelpCircle size={15} strokeWidth={1.5} />
          </button>
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

        {loading ? (
          <div className="empty-state" role="status" aria-live="polite" style={{ padding: '32px 0', textAlign: 'center' }}>
            <Loader2 size={20} style={{ color: 'var(--text-muted)', marginBottom: 8, animation: 'spin 1s linear infinite' }} />
            <span className="sr-only">Загрузка...</span>
            <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>
              Вычисляем статистику…
            </div>
          </div>
        ) : fetchError ? (
          <div className="empty-state" style={{ padding: '32px 0', textAlign: 'center' }}>
            <div style={{ marginBottom: 8, color: 'var(--text-muted)', fontSize: 13 }}>
              Не удалось загрузить данные анализа
            </div>
            <button
              type="button"
              className="btn btn-secondary"
              style={{ fontSize: 12, marginTop: 4 }}
              onClick={() => {
                setFetchError(false);
                setLoading(true);
                fetchImpactForEvent(event, activeWindow).then((data) => {
                  setImpact(data);
                  setFetchError(data === null);
                  setLoading(false);
                });
              }}
            >
              Повторить
            </button>
          </div>
        ) : impact ? (
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

            {/* Custom metrics */}
            {customMetrics.length > 0 && (
              <div className="impact-metrics-grid" style={{ marginTop: 8 }}>
                {customMetrics.map((m) => (
                  <div key={m} className="metric-compare-card" style={{ opacity: 0.7, position: 'relative' }}>
                    <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-muted)', marginBottom: 4 }}>{m}</div>
                    <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>Данные накапливаются…</div>
                    <button
                      type="button"
                      onClick={() => setCustomMetrics((prev) => prev.filter((x) => x !== m))}
                      style={{ position: 'absolute', top: 6, right: 6, background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)', padding: 2 }}
                    >
                      <X size={11} />
                    </button>
                  </div>
                ))}
              </div>
            )}

            {/* Add chart */}
            <div className="impact-add-chart-row">
              <select
                className="impact-add-chart-select"
                value={selectedMetric}
                onChange={(e) => setSelectedMetric(e.target.value)}
              >
                <option value="">Выберите метрику...</option>
                <option value="Lying time per cow, per day">Lying time per cow, per day</option>
                <option value="Steps per cow, per day">Steps per cow, per day</option>
                <option value="SCC individual">SCC individual</option>
                <option value="Body condition score">Body condition score</option>
                <option value="Feed push frequency">Feed push frequency</option>
              </select>
              <button className="impact-add-chart-btn" type="button" onClick={handleAddMetric}>
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
              Анализ влияния появится автоматически после накопления достаточного количества данных
            </div>
          </div>
        )}
      </div>
    </div>
    {addToast && <div className="toast" role="status">{addToast}</div>}
    </>
  );
}
