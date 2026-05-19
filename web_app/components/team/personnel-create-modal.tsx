'use client';

import { useState } from 'react';
import { Modal } from '@/components/ui/modal';
import {
  createPersonnel,
  validatePersonnelCreate,
  type PersonnelValidationError,
} from '@/lib/api/personnel';
import type { Personnel, PersonnelCreateRequest } from '@/lib/api/contracts';

type Props = {
  open: boolean;
  onClose: () => void;
  onCreated?: (person: Personnel) => void;
};

type FormState = {
  full_name: string;
  position: string;
  group_id: string;
  phone: string;
  email: string;
  hired_at: string;
};

const EMPTY: FormState = {
  full_name: '',
  position: '',
  group_id: '',
  phone: '',
  email: '',
  hired_at: '',
};

function toRequest(form: FormState): PersonnelCreateRequest {
  const out: PersonnelCreateRequest = {
    full_name: form.full_name.trim(),
    position: form.position.trim(),
  };
  if (form.group_id.trim()) out.group_id = form.group_id.trim();
  if (form.phone.trim()) out.phone = form.phone.trim();
  if (form.email.trim()) out.email = form.email.trim();
  if (form.hired_at.trim()) out.hired_at = form.hired_at.trim();
  return out;
}

export function PersonnelCreateModal({ open, onClose, onCreated }: Props) {
  const [form, setForm] = useState<FormState>(EMPTY);
  const [errors, setErrors] = useState<PersonnelValidationError[]>([]);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  if (!open) return null;

  const errorFor = (field: keyof FormState): string | undefined =>
    errors.find((e) => e.field === field)?.message;

  const reset = () => {
    setForm(EMPTY);
    setErrors([]);
    setSubmitError(null);
    setSubmitting(false);
  };

  const handleClose = () => {
    reset();
    onClose();
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitError(null);
    const body = toRequest(form);
    const validation = validatePersonnelCreate(body);
    if (validation.length > 0) {
      setErrors(validation);
      return;
    }
    setErrors([]);
    setSubmitting(true);
    try {
      const resp = await createPersonnel(body);
      onCreated?.(resp.item);
      reset();
      onClose();
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : 'Не удалось создать сотрудника');
      setSubmitting(false);
    }
  };

  return (
    <Modal open={open} onClose={handleClose} title="Добавить сотрудника" width={520}>
      <form className="personnel-create-form" onSubmit={handleSubmit}>
        <div className="form-row">
          <label htmlFor="pc-name">ФИО *</label>
          <input
            id="pc-name"
            type="text"
            value={form.full_name}
            onChange={(e) => setForm({ ...form, full_name: e.target.value })}
            required
            autoFocus
          />
          {errorFor('full_name') ? <span className="form-error">{errorFor('full_name')}</span> : null}
        </div>
        <div className="form-row">
          <label htmlFor="pc-pos">Должность *</label>
          <input
            id="pc-pos"
            type="text"
            value={form.position}
            onChange={(e) => setForm({ ...form, position: e.target.value })}
            required
            placeholder="Например: зоотехник, ветврач"
          />
          {errorFor('position') ? <span className="form-error">{errorFor('position')}</span> : null}
        </div>
        <div className="form-row">
          <label htmlFor="pc-group">Группа / отдел</label>
          <input
            id="pc-group"
            type="text"
            value={form.group_id}
            onChange={(e) => setForm({ ...form, group_id: e.target.value })}
            placeholder="ID группы (например, PEN_LACT_1)"
          />
        </div>
        <div className="form-row">
          <label htmlFor="pc-phone">Телефон</label>
          <input
            id="pc-phone"
            type="tel"
            value={form.phone}
            onChange={(e) => setForm({ ...form, phone: e.target.value })}
            placeholder="+7 ___ ___ __ __"
          />
        </div>
        <div className="form-row">
          <label htmlFor="pc-email">Email</label>
          <input
            id="pc-email"
            type="email"
            value={form.email}
            onChange={(e) => setForm({ ...form, email: e.target.value })}
            placeholder="user@example.com"
          />
          {errorFor('email') ? <span className="form-error">{errorFor('email')}</span> : null}
        </div>
        <div className="form-row">
          <label htmlFor="pc-hired">Дата приёма на работу</label>
          <input
            id="pc-hired"
            type="date"
            value={form.hired_at}
            onChange={(e) => setForm({ ...form, hired_at: e.target.value })}
          />
        </div>
        {submitError ? <div className="form-submit-error" role="alert">{submitError}</div> : null}
        <div className="form-actions">
          <button type="button" className="button button-secondary" onClick={handleClose} disabled={submitting}>
            Отмена
          </button>
          <button type="submit" className="button button-primary" disabled={submitting}>
            {submitting ? 'Создаём…' : 'Создать'}
          </button>
        </div>
      </form>
    </Modal>
  );
}
