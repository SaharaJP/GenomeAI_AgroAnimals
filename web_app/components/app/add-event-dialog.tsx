'use client';

import { useCallback, useEffect, useState } from 'react';
import { Paperclip, X } from 'lucide-react';
import type { TimelineEvent } from '@/lib/api/timeline';
import { EventTypeSelect, EVENT_TYPE_OPTIONS } from './event-type-select';
import { useAddEvent } from './add-event-context';

const AFFECTED_GROUPS = [
  { value: 'all',      label: 'Все коровы' },
  { value: 'milking',  label: 'Дойные' },
  { value: 'close_up', label: 'Close-up' },
  { value: 'fresh',    label: 'Fresh cows' },
  { value: 'group_1',  label: 'Группа 1' },
  { value: 'group_2',  label: 'Группа 2' },
  { value: 'group_3',  label: 'Группа 3' },
  { value: 'group_4',  label: 'Группа 4' },
  { value: 'group_5',  label: 'Группа 5' },
];

function todayIso() {
  return new Date().toISOString().split('T')[0];
}

export function AddEventDialog() {
  const { isOpen, closeDialog, appendUserEvent } = useAddEvent();

  const [eventType, setEventType] = useState('ration_change');
  const [date, setDate] = useState(todayIso);
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [groups, setGroups] = useState<string[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [fieldError, setFieldError] = useState('');
  const [toastMsg, setToastMsg] = useState('');

  const typeOption = EVENT_TYPE_OPTIONS.find((o) => o.value === eventType) ?? EVENT_TYPE_OPTIONS[0];

  const resetForm = useCallback(() => {
    setEventType('ration_change');
    setDate(todayIso());
    setTitle('');
    setDescription('');
    setGroups([]);
    setFieldError('');
    setSubmitting(false);
  }, []);

  useEffect(() => {
    if (!isOpen) resetForm();
  }, [isOpen, resetForm]);

  useEffect(() => {
    if (!isOpen) return;
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') closeDialog(); };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [isOpen, closeDialog]);

  function toggleGroup(val: string) {
    setGroups((prev) =>
      prev.includes(val) ? prev.filter((g) => g !== val) : [...prev, val],
    );
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!title.trim()) {
      setFieldError('Введите заголовок события');
      return;
    }
    setFieldError('');
    setSubmitting(true);
    try {
      const res = await fetch('/api/backend/timeline/events', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({
          event_type: eventType,
          date,
          title: title.trim(),
          description: description.trim(),
          affected_groups: groups,
        }),
      });

      let data: { event?: { timeline_event_id?: string }; event_id?: string } = {};
      try { data = await res.json(); } catch { /* ignore parse error */ }

      const newEvent: TimelineEvent = {
        timeline_event_id:
          data.event?.timeline_event_id ?? data.event_id ?? `TL_local_${Date.now()}`,
        date,
        event_type: eventType,
        title: title.trim(),
        body: description.trim(),
        source: 'Добавлено вручную',
        has_impact: false,
      };

      appendUserEvent(newEvent);
      closeDialog();
      setToastMsg('Событие добавлено в Ленту. Результаты будут готовы через ~24ч.');
      setTimeout(() => setToastMsg(''), 4000);
    } catch {
      setFieldError('Ошибка сохранения. Попробуйте ещё раз.');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <>
      {isOpen && (
        <div
          className="ae-overlay"
          onClick={(e) => e.target === e.currentTarget && closeDialog()}
        >
          <div
            className="ae-dialog"
            role="dialog"
            aria-modal="true"
            aria-label="Добавить событие"
          >
            <div className="ae-dialog-header">
              <h2 className="ae-dialog-title">Добавить событие</h2>
              <button
                className="an-dialog-close"
                onClick={closeDialog}
                aria-label="Закрыть"
                type="button"
              >
                <X size={16} />
              </button>
            </div>

            <form className="ae-dialog-body" onSubmit={handleSubmit} noValidate>
              <div className="ae-field">
                <label className="ae-label">Тип события</label>
                <EventTypeSelect value={eventType} onChange={setEventType} />
              </div>

              <div className="ae-row">
                <div className="ae-field ae-field--half">
                  <label className="ae-label" htmlFor="ae-date">Дата</label>
                  <input
                    id="ae-date"
                    className="input"
                    type="date"
                    value={date}
                    onChange={(e) => setDate(e.target.value)}
                    required
                  />
                </div>
              </div>

              <div className="ae-field">
                <label className="ae-label" htmlFor="ae-title">
                  Заголовок <span className="ae-required">*</span>
                </label>
                <input
                  id="ae-title"
                  className="input"
                  type="text"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder={typeOption.placeholder}
                  maxLength={200}
                  required
                />
              </div>

              <div className="ae-field">
                <label className="ae-label" htmlFor="ae-desc">Описание</label>
                <textarea
                  id="ae-desc"
                  className="input ae-textarea"
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="Опишите детали изменения..."
                  rows={3}
                />
              </div>

              <div className="ae-field">
                <label className="ae-label">Затронутые группы</label>
                <div className="ae-groups">
                  {AFFECTED_GROUPS.map((g) => (
                    <button
                      key={g.value}
                      type="button"
                      className={`ae-group-chip${groups.includes(g.value) ? ' ae-group-chip--active' : ''}`}
                      onClick={() => toggleGroup(g.value)}
                    >
                      {g.label}
                    </button>
                  ))}
                </div>
              </div>

              <div className="ae-field">
                <label className="ae-label">Прикрепить файл</label>
                <div className="ae-attach-stub">
                  <Paperclip size={14} />
                  <span>Прикрепить файл (например PDF с лабораторными)</span>
                </div>
              </div>

              {fieldError && <p className="ae-error">{fieldError}</p>}

              <div className="ae-dialog-footer">
                <button
                  type="button"
                  className="btn-outline"
                  onClick={closeDialog}
                >
                  Отмена
                </button>
                <button
                  type="submit"
                  className="btn-primary-teal"
                  disabled={submitting}
                >
                  {submitting ? 'Сохранение...' : 'Добавить'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {toastMsg && (
        <div className="toast ae-toast-success" role="status" aria-live="polite">
          {toastMsg}
        </div>
      )}
    </>
  );
}
