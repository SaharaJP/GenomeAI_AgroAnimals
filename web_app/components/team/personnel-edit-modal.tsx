'use client';

import { useEffect, useState } from 'react';
import { Modal } from '@/components/ui/modal';
import {
  buildPersonnelPatch,
  updatePersonnel,
  validatePersonnelUpdate,
  type PersonnelValidationError,
} from '@/lib/api/personnel';
import type { Personnel, PersonnelUpdateRequest } from '@/lib/api/contracts';

type Props = {
  open: boolean;
  person: Personnel;
  piiVisible: boolean;
  onClose: () => void;
  onSaved?: (updated: Personnel) => void;
};

type FormState = Required<{
  full_name: string;
  position: string;
  group_id: string;
  phone: string;
  email: string;
  hired_at: string;
  user_id: string;
}>;

function toFormState(person: Personnel): FormState {
  return {
    full_name: person.full_name ?? '',
    position: person.position ?? '',
    group_id: person.group_id ?? '',
    phone: person.phone ?? '',
    email: person.email ?? '',
    hired_at: person.hired_at ?? '',
    user_id: person.user_id != null ? String(person.user_id) : '',
  };
}

function formToInitialRequest(person: Personnel): PersonnelUpdateRequest {
  return {
    full_name: person.full_name ?? null,
    position: person.position ?? null,
    group_id: person.group_id ?? null,
    phone: person.phone ?? null,
    email: person.email ?? null,
    hired_at: person.hired_at ?? null,
    user_id: person.user_id ?? null,
  };
}

function formToNextRequest(form: FormState): PersonnelUpdateRequest {
  const userIdRaw = form.user_id.trim();
  return {
    full_name: form.full_name,
    position: form.position,
    group_id: form.group_id.trim() || null,
    phone: form.phone.trim() || null,
    email: form.email.trim() || null,
    hired_at: form.hired_at.trim() || null,
    user_id: userIdRaw ? Number(userIdRaw) : null,
  };
}

export function PersonnelEditModal({ open, person, piiVisible, onClose, onSaved }: Props) {
  const [form, setForm] = useState<FormState>(() => toFormState(person));
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [showErrors, setShowErrors] = useState(false);

  useEffect(() => {
    if (open) {
      setForm(toFormState(person));
      setSubmitError(null);
      setShowErrors(false);
      setSubmitting(false);
    }
  }, [open, person]);

  const initial = formToInitialRequest(person);
  const next = formToNextRequest(form);
  const patch = buildPersonnelPatch(initial, next);
  const errors: PersonnelValidationError[] = validatePersonnelUpdate(next);
  const userIdInvalid = form.user_id.trim() !== '' && !Number.isFinite(Number(form.user_id.trim()));

  const errorByField = (field: PersonnelValidationError['field']) =>
    showErrors ? errors.find((e) => e.field === field)?.message : undefined;

  const canSubmit =
    Object.keys(patch).length > 0 && errors.length === 0 && !userIdInvalid && !submitting;

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setShowErrors(true);
    if (!canSubmit) return;
    setSubmitting(true);
    setSubmitError(null);
    try {
      const resp = await updatePersonnel(person.personnel_id, patch);
      onSaved?.(resp.item);
      onClose();
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : 'Ошибка сохранения');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal open={open} onClose={onClose} title="Редактировать сотрудника">
      <form onSubmit={onSubmit} className="task-create-form">
        <label className="task-create-form__field">
          <span className="task-create-form__label">ФИО *</span>
          <input
            type="text"
            value={form.full_name}
            onChange={(e) => setForm({ ...form, full_name: e.target.value })}
            maxLength={200}
            autoFocus
          />
          {errorByField('full_name') ? (
            <span className="task-create-form__error">{errorByField('full_name')}</span>
          ) : null}
        </label>

        <label className="task-create-form__field">
          <span className="task-create-form__label">Должность *</span>
          <input
            type="text"
            value={form.position}
            onChange={(e) => setForm({ ...form, position: e.target.value })}
            maxLength={200}
          />
          {errorByField('position') ? (
            <span className="task-create-form__error">{errorByField('position')}</span>
          ) : null}
        </label>

        <label className="task-create-form__field">
          <span className="task-create-form__label">Группа</span>
          <input
            type="text"
            value={form.group_id}
            onChange={(e) => setForm({ ...form, group_id: e.target.value })}
            placeholder="Свободный формат: Ветеринары, Зоотехники…"
          />
        </label>

        {piiVisible ? (
          <>
            <div className="task-create-form__row">
              <label className="task-create-form__field">
                <span className="task-create-form__label">Телефон</span>
                <input
                  type="text"
                  value={form.phone}
                  onChange={(e) => setForm({ ...form, phone: e.target.value })}
                  placeholder="+7…"
                />
              </label>
              <label className="task-create-form__field">
                <span className="task-create-form__label">Email</span>
                <input
                  type="text"
                  value={form.email}
                  onChange={(e) => setForm({ ...form, email: e.target.value })}
                  placeholder="user@example.com"
                />
                {errorByField('email') ? (
                  <span className="task-create-form__error">{errorByField('email')}</span>
                ) : null}
              </label>
            </div>
            <div className="task-create-form__row">
              <label className="task-create-form__field">
                <span className="task-create-form__label">Принят</span>
                <input
                  type="date"
                  value={form.hired_at}
                  onChange={(e) => setForm({ ...form, hired_at: e.target.value })}
                />
              </label>
              <label className="task-create-form__field">
                <span className="task-create-form__label">user_id (auth)</span>
                <input
                  type="number"
                  value={form.user_id}
                  onChange={(e) => setForm({ ...form, user_id: e.target.value })}
                  placeholder="пусто = отвязать"
                />
                {userIdInvalid ? (
                  <span className="task-create-form__error">Должно быть числом</span>
                ) : null}
              </label>
            </div>
          </>
        ) : (
          <p className="task-create-form__hint">Контактные данные скрыты — нет права personnel.read_pii.</p>
        )}

        {submitError ? (
          <p className="task-create-form__error" role="alert">
            {submitError}
          </p>
        ) : null}

        <div className="task-create-form__actions">
          <button type="button" className="btn-outline" onClick={onClose} disabled={submitting}>
            Отмена
          </button>
          <button type="submit" className="btn-primary-teal" disabled={!canSubmit}>
            {submitting ? 'Сохраняем…' : Object.keys(patch).length === 0 ? 'Нет изменений' : 'Сохранить'}
          </button>
        </div>
      </form>
    </Modal>
  );
}
