'use client';

import { useEffect, useState } from 'react';
import { Modal } from '@/components/ui/modal';
import { apiFetch } from '@/lib/api/client';
import {
  createWorklist,
  fetchTeams,
  validateWorklistInput,
  type WorklistValidationError,
} from '@/lib/api/worklists';
import type {
  Personnel,
  PersonnelListResponse,
  TeamCatalogEntry,
  WorklistCreateRequest,
  WorklistCreateResponse,
} from '@/lib/api/contracts';

type Mode = 'team' | 'personal';

type Props = {
  open: boolean;
  onClose: () => void;
  onCreated?: (resp: WorklistCreateResponse) => void;
};

export function TaskCreateModal({ open, onClose, onCreated }: Props) {
  const [mode, setMode] = useState<Mode>('team');
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [priority, setPriority] = useState<number>(3);
  const [dueAt, setDueAt] = useState('');
  const [assigneeTeam, setAssigneeTeam] = useState('');
  const [ownerUserId, setOwnerUserId] = useState<number | ''>('');

  const [teams, setTeams] = useState<TeamCatalogEntry[]>([]);
  const [personnel, setPersonnel] = useState<Personnel[]>([]);
  const [loadingCatalogs, setLoadingCatalogs] = useState(false);
  const [catalogError, setCatalogError] = useState<string | null>(null);

  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [showErrors, setShowErrors] = useState(false);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setLoadingCatalogs(true);
    setCatalogError(null);
    Promise.all([
      fetchTeams(),
      apiFetch<PersonnelListResponse>('/personnel?limit=200'),
    ])
      .then(([teamsResp, personnelResp]) => {
        if (cancelled) return;
        setTeams(teamsResp.teams || []);
        setPersonnel((personnelResp.items || []).filter((p) => p.user_id != null));
      })
      .catch((err) => {
        if (cancelled) return;
        setCatalogError(err instanceof Error ? err.message : 'Не удалось загрузить справочники');
      })
      .finally(() => {
        if (!cancelled) setLoadingCatalogs(false);
      });
    return () => {
      cancelled = true;
    };
  }, [open]);

  useEffect(() => {
    if (!open) {
      setMode('team');
      setTitle('');
      setDescription('');
      setPriority(3);
      setDueAt('');
      setAssigneeTeam('');
      setOwnerUserId('');
      setSubmitError(null);
      setShowErrors(false);
      setSubmitting(false);
    }
  }, [open]);

  const buildInput = (): WorklistCreateRequest => ({
    title,
    priority,
    due_at: dueAt || null,
    description: description.trim() || null,
    assignee_team: mode === 'team' && assigneeTeam ? assigneeTeam : null,
    owner_user_id: mode === 'personal' && typeof ownerUserId === 'number' ? ownerUserId : null,
  });

  const errors: WorklistValidationError[] = validateWorklistInput(buildInput());
  const errorByField = (field: WorklistValidationError['field']) =>
    showErrors ? errors.find((e) => e.field === field)?.message : undefined;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setShowErrors(true);
    if (errors.length > 0) return;
    setSubmitting(true);
    setSubmitError(null);
    try {
      const resp = await createWorklist(buildInput());
      onCreated?.(resp);
      onClose();
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : 'Ошибка при создании задачи');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal open={open} onClose={onClose} title="Поставить задачу">
      <form onSubmit={handleSubmit} className="task-create-form">
        <div className="task-create-form__mode" role="tablist" aria-label="Тип задачи">
          <button
            type="button"
            role="tab"
            aria-selected={mode === 'team'}
            className={`window-tab${mode === 'team' ? ' window-tab--active' : ''}`}
            onClick={() => setMode('team')}
          >
            Командная
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={mode === 'personal'}
            className={`window-tab${mode === 'personal' ? ' window-tab--active' : ''}`}
            onClick={() => setMode('personal')}
          >
            Личная
          </button>
        </div>

        <label className="task-create-form__field">
          <span className="task-create-form__label">Заголовок *</span>
          <input
            type="text"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            maxLength={200}
            placeholder="Что нужно сделать"
            autoFocus
          />
          {errorByField('title') ? <span className="task-create-form__error">{errorByField('title')}</span> : null}
        </label>

        {mode === 'team' ? (
          <label className="task-create-form__field">
            <span className="task-create-form__label">Команда *</span>
            <select value={assigneeTeam} onChange={(e) => setAssigneeTeam(e.target.value)} disabled={loadingCatalogs}>
              <option value="">— выберите команду —</option>
              {teams.map((t) => (
                <option key={t.key} value={t.key}>
                  {t.title} ({t.key})
                </option>
              ))}
            </select>
            {errorByField('assignment') ? (
              <span className="task-create-form__error">{errorByField('assignment')}</span>
            ) : null}
          </label>
        ) : (
          <label className="task-create-form__field">
            <span className="task-create-form__label">Ответственный *</span>
            <select
              value={ownerUserId === '' ? '' : String(ownerUserId)}
              onChange={(e) => setOwnerUserId(e.target.value ? Number(e.target.value) : '')}
              disabled={loadingCatalogs}
            >
              <option value="">— выберите сотрудника —</option>
              {personnel.map((p) => (
                <option key={p.personnel_id} value={String(p.user_id)}>
                  {p.full_name} ({p.position})
                </option>
              ))}
            </select>
            {errorByField('assignment') ? (
              <span className="task-create-form__error">{errorByField('assignment')}</span>
            ) : null}
            {personnel.length === 0 && !loadingCatalogs ? (
              <span className="task-create-form__hint">
                Нет сотрудников с привязанным auth-аккаунтом. Привяжите user_id в карточке сотрудника.
              </span>
            ) : null}
          </label>
        )}

        <div className="task-create-form__row">
          <label className="task-create-form__field">
            <span className="task-create-form__label">Приоритет</span>
            <select value={priority} onChange={(e) => setPriority(Number(e.target.value))}>
              <option value={1}>1 — низкий</option>
              <option value={2}>2</option>
              <option value={3}>3 — средний</option>
              <option value={4}>4</option>
              <option value={5}>5 — высокий</option>
            </select>
          </label>

          <label className="task-create-form__field">
            <span className="task-create-form__label">Срок</span>
            <input type="date" value={dueAt} onChange={(e) => setDueAt(e.target.value)} />
          </label>
        </div>

        <label className="task-create-form__field">
          <span className="task-create-form__label">Описание</span>
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={4}
            maxLength={2000}
            placeholder="Контекст, ссылки, детали"
          />
        </label>

        {catalogError ? (
          <p className="task-create-form__error" role="alert">
            {catalogError}
          </p>
        ) : null}
        {submitError ? (
          <p className="task-create-form__error" role="alert">
            {submitError}
          </p>
        ) : null}

        <div className="task-create-form__actions">
          <button type="button" className="btn-outline" onClick={onClose} disabled={submitting}>
            Отмена
          </button>
          <button type="submit" className="btn-primary-teal" disabled={submitting || loadingCatalogs}>
            {submitting ? 'Создаём…' : 'Создать задачу'}
          </button>
        </div>
      </form>
    </Modal>
  );
}
