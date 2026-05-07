'use client';

import { useCallback, useEffect, useState } from 'react';
import { Paperclip, X, Search } from 'lucide-react';
import type { TimelineEvent } from '@/lib/api/timeline';
import { EventTypeSelect, EVENT_TYPE_OPTIONS } from './event-type-select';
import { useAddEvent } from './add-event-context';

type AnimalLite = { animal_id: string; breed?: string; pen_id?: string; status?: string };

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

  // Individual animal selection
  const [animalQuery, setAnimalQuery] = useState('');
  const [animalSuggestions, setAnimalSuggestions] = useState<AnimalLite[]>([]);
  const [animalIds, setAnimalIds] = useState<string[]>([]);
  const [animalLoading, setAnimalLoading] = useState(false);

  const typeOption = EVENT_TYPE_OPTIONS.find((o) => o.value === eventType) ?? EVENT_TYPE_OPTIONS[0];

  const resetForm = useCallback(() => {
    setEventType('ration_change');
    setDate(todayIso());
    setTitle('');
    setDescription('');
    setGroups([]);
    setAnimalIds([]);
    setAnimalQuery('');
    setAnimalSuggestions([]);
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

  // Live-search animals by id (debounced)
  useEffect(() => {
    if (!isOpen) return;
    const q = animalQuery.trim();
    if (!q) {
      setAnimalSuggestions([]);
      return;
    }
    let cancelled = false;
    setAnimalLoading(true);
    const handle = setTimeout(async () => {
      try {
        const res = await fetch(
          `/api/backend/api/app/v1/animals?limit=20&search=${encodeURIComponent(q)}`,
          { cache: 'no-store' },
        );
        if (!res.ok) throw new Error('bad status');
        const data = await res.json();
        if (!cancelled) setAnimalSuggestions(data.animals ?? []);
      } catch {
        if (!cancelled) setAnimalSuggestions([]);
      } finally {
        if (!cancelled) setAnimalLoading(false);
      }
    }, 250);
    return () => { cancelled = true; clearTimeout(handle); };
  }, [animalQuery, isOpen]);

  function toggleAnimal(id: string) {
    setAnimalIds((prev) => prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]);
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
      const res = await fetch('/api/backend/api/timeline/events', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({
          event_type: eventType,
          date,
          title: title.trim(),
          description: description.trim(),
          affected_groups: groups,
          animal_ids: animalIds,
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
                <label className="ae-label">Конкретные животные (опционально)</label>
                <div style={{ position: 'relative' }}>
                  <Search size={13} style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)' }} />
                  <input
                    className="input"
                    placeholder="Поиск по ID животного..."
                    value={animalQuery}
                    onChange={(e) => setAnimalQuery(e.target.value)}
                    style={{ paddingLeft: 32, width: '100%', boxSizing: 'border-box' }}
                  />
                </div>

                {animalIds.length > 0 && (
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginTop: 6 }}>
                    {animalIds.map((id) => (
                      <span
                        key={id}
                        className="badge badge-success"
                        style={{ fontSize: 11, display: 'inline-flex', alignItems: 'center', gap: 4 }}
                      >
                        {id}
                        <button
                          type="button"
                          aria-label={`Убрать ${id}`}
                          onClick={() => toggleAnimal(id)}
                          style={{
                            background: 'none', border: 'none', cursor: 'pointer',
                            padding: 0, color: 'inherit', display: 'inline-flex',
                          }}
                        >
                          <X size={10} />
                        </button>
                      </span>
                    ))}
                  </div>
                )}

                {animalQuery.trim() && (
                  <div
                    style={{
                      marginTop: 4,
                      maxHeight: 160, overflowY: 'auto',
                      border: '1px solid var(--border)', borderRadius: 8,
                      background: 'var(--surface, #fff)',
                    }}
                  >
                    {animalLoading ? (
                      <div style={{ padding: 8, fontSize: 12, color: 'var(--text-muted)' }}>
                        Поиск…
                      </div>
                    ) : animalSuggestions.length === 0 ? (
                      <div style={{ padding: 8, fontSize: 12, color: 'var(--text-muted)' }}>
                        Не найдено
                      </div>
                    ) : (
                      animalSuggestions.map((a) => {
                        const picked = animalIds.includes(a.animal_id);
                        return (
                          <button
                            key={a.animal_id}
                            type="button"
                            onClick={() => toggleAnimal(a.animal_id)}
                            style={{
                              display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                              width: '100%', padding: '6px 10px',
                              background: picked ? 'var(--teal-light, #e6f7f5)' : 'transparent',
                              border: 'none', borderBottom: '1px solid var(--border)',
                              cursor: 'pointer', fontSize: 13, color: 'var(--text)',
                              textAlign: 'left',
                            }}
                          >
                            <span style={{ fontWeight: 600 }}>{a.animal_id}</span>
                            <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                              {[a.breed, a.pen_id, a.status].filter(Boolean).join(' · ')}
                            </span>
                          </button>
                        );
                      })
                    )}
                  </div>
                )}
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
