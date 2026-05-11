'use client';

import dynamic from 'next/dynamic';
import { useState, useEffect, useCallback, useRef } from 'react';
import { X, HelpCircle } from 'lucide-react';
import { DEMO_TIMELINE_EVENTS } from '@/lib/api/timeline';
import type { MetricWindow, TimelineEvent } from '@/lib/api/timeline';
import { EventList } from '@/components/timeline/event-list';
import { useAddEvent } from '@/components/app/add-event-context';
import { pathLabels } from '@/lib/navigation';

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

function EditEventDialog({
  event,
  onClose,
  onSaved,
}: {
  event: TimelineEvent;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [title, setTitle] = useState(event.title);
  const [body, setBody] = useState(event.body ?? '');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    if (!title.trim()) { setError('Введите заголовок'); return; }
    setSaving(true);
    try {
      const res = await fetch(`/api/backend/api/timeline/events/${event.timeline_event_id}`, {
        method: 'PATCH',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ title: title.trim(), body: body.trim() }),
      });
      if (!res.ok) throw new Error('bad status');
      onSaved();
      onClose();
    } catch {
      setError('Ошибка сохранения');
    } finally {
      setSaving(false);
    }
  }

  return (
    <div
      className="ae-overlay"
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div className="ae-dialog" role="dialog" aria-modal="true" aria-label="Редактировать событие">
        <div className="ae-dialog-header">
          <h2 className="ae-dialog-title">Редактировать событие</h2>
          <button className="an-dialog-close" onClick={onClose} aria-label="Закрыть" type="button">
            <X size={16} />
          </button>
        </div>
        <form className="ae-dialog-body" onSubmit={handleSave} noValidate>
          <div className="ae-field">
            <label className="ae-label" htmlFor="edit-title">Заголовок <span className="ae-required">*</span></label>
            <input
              id="edit-title"
              className="input"
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              maxLength={200}
              required
            />
          </div>
          <div className="ae-field">
            <label className="ae-label" htmlFor="edit-body">Описание</label>
            <textarea
              id="edit-body"
              className="input ae-textarea"
              value={body}
              onChange={(e) => setBody(e.target.value)}
              rows={3}
            />
          </div>
          {error && <p className="ae-error">{error}</p>}
          <div className="ae-dialog-footer">
            <button type="button" className="btn-outline" onClick={onClose}>Отмена</button>
            <button type="submit" className="btn-primary-teal" disabled={saving}>
              {saving ? 'Сохранение...' : 'Сохранить'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

export default function TimelinePage() {
  const { openDialog, userEvents } = useAddEvent();

  const [dbEvents, setDbEvents] = useState<TimelineEvent[]>([]);
  const [editingEvent, setEditingEvent] = useState<TimelineEvent | null>(null);
  const [toast, setToast] = useState('');
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

  function showToast(msg: string) {
    setToast(msg);
    setTimeout(() => setToast(''), 3500);
  }

  async function handleDeleteEvent(event: TimelineEvent) {
    if (!confirm(`Удалить событие «${event.title}»?`)) return;
    try {
      await fetch(`/api/backend/api/timeline/events/${event.timeline_event_id}`, { method: 'DELETE' });
      if (selectedId === event.timeline_event_id) setSelectedId(null);
      fetchDbEvents();
      showToast('Событие удалено');
    } catch {
      showToast('Ошибка удаления');
    }
  }

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

  function handleDownloadHelp() {
    const text = `GenomeAI AgroAnimals — инструкции и математика системы
================================================================

ОБЩАЯ КАРТА СИСТЕМЫ
• ${pathLabels['/dashboard']} (/dashboard) — KPI стада: надой, ECM, СКК, маржа.
• ${pathLabels['/daily-summary']} (/daily-summary) — ежедневная сводка: алерты, действия, задачи.
• ${pathLabels['/insights']} (/insights) — алерты со сценариями реакции (acknowledge / resolve).
• ${pathLabels['/analytics']} (/analytics) — графики по 8 группам метрик: продуктивность, корм,
  воспроизводство, здоровье, поведение, состав стада, погода, финансы.
• ${pathLabels['/timeline']} (/timeline) — хронология управленческих событий и их влияние.
• ${pathLabels['/profiles/animal']} (/profiles/animal) — список и профили коров, фильтр по породе/статусу/группе.
• ${pathLabels['/copilot']} (/copilot) — генерация недельных бриф-отчётов и Q&A.
• ${pathLabels['/worklists']} (/worklists) — задачи на сегодня с привязкой к решениям.

МЕТОДОЛОГИЯ ВЛИЯНИЯ СОБЫТИЙ
Лента событий сопоставляет управленческие решения с динамикой ключевых метрик стада.
Для каждого события система формирует "до" и "после" на основе выбранного окна.

ВРЕМЕННЫЕ ОКНА
• 1 день  — 1 день до и 1 день после события
• 3 дня   — 3 дня до и 3 дня после
• 7 дней  — 7 дней до и 7 дней после
• 14 дней — 14 дней до и 14 дней после

ОСНОВНЫЕ МЕТРИКИ
• Надой (кг/гол/день)        — основная производственная метрика
• ECM (кг/гол/день)         — энергокорректированное молоко
• Жир / белок (%)           — качество молока
• СКК (тыс/мл)              — соматические клетки, индикатор здоровья вымени
• DMI (кг СВ/гол/день)      — потребление сухого вещества
• Жвачка (мин/гол/день)     — поведенческая метрика
• Активность (индекс)       — поведенческая метрика
• THI (индекс)              — индекс тепловой нагрузки
• Pregnancy / Conception (%) — показатели воспроизводства
• Days open (дн)            — дни открытого периода

РАСЧЁТ ИЗМЕНЕНИЯ
Δ      = (среднее "после") − (среднее "до")
Δ%     = Δ / среднее "до" × 100%
p-value = критерий Уэлча (Welch's t-test) на различие средних
CI 95%  = bootstrap 1000 реплик
Эффект  = классификация по |Cohen's d| (negligible / small / medium / large)

ЦВЕТОВАЯ ЛОГИКА
Зелёный — улучшение метрики относительно "до".
Красный — ухудшение.
Серый   — статистически незначимое изменение.

КОГДА АНАЛИЗ НЕ ПРОВОДИТСЯ
• Событие добавлено пользователем вручную и has_impact=false → анализ начнётся
  автоматически после накопления статистики (обычно через 24–48 часов после события).
• Окно меньше 1 дня от события — данных "после" ещё нет.
• Меньше 5 наблюдений на стороне (treated/control) — выборка недостоверна.

КОРОТКО О ДОСТОВЕРНОСТИ
• Анализ носит информационный характер и не заменяет ветеринарное заключение.
• Для надёжных выводов рекомендуется окно ≥ 7 дней.
• Корреляция не означает причинно-следственную связь.

GenomeAI AgroAnimals © ${new Date().getFullYear()}
`;
    const blob = new Blob([text], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'genomeai-help-bundle.txt';
    a.click();
    URL.revokeObjectURL(url);
    showToast('Архив инструкций скачан');
  }

  return (
    <>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
        <h1 className="page-title" style={{ margin: 0 }}>Лента событий</h1>
        <button
          type="button"
          onClick={handleDownloadHelp}
          title="Скачать архив инструкций по системе и математике"
          aria-label="Скачать архив инструкций"
          style={{
            background: 'none', border: 'none', cursor: 'pointer',
            color: 'var(--text-muted)', padding: 4,
            display: 'inline-flex', alignItems: 'center',
          }}
        >
          <HelpCircle size={18} strokeWidth={1.5} />
        </button>
      </div>
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
          onDeleteEvent={handleDeleteEvent}
          onEditEvent={setEditingEvent}
        />

        <ImpactPanel
          event={selectedEvent}
          window={activeWindow}
          onWindowChange={setActiveWindow}
        />
      </div>

      {editingEvent && (
        <EditEventDialog
          event={editingEvent}
          onClose={() => setEditingEvent(null)}
          onSaved={() => { fetchDbEvents(); showToast('Событие обновлено'); }}
        />
      )}

      {toast && <div className="toast" role="status">{toast}</div>}
    </>
  );
}
