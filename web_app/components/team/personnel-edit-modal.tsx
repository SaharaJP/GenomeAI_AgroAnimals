'use client';

import { useEffect, useRef, useState } from 'react';
import { Modal } from '@/components/ui/modal';
import {
  buildPersonnelPatch,
  deletePersonnelPhoto,
  getPersonnelPhotoUrl,
  updatePersonnel,
  uploadPersonnelPhoto,
  validatePersonnelUpdate,
  type PersonnelValidationError,
} from '@/lib/api/personnel';
import type { Personnel, PersonnelUpdateRequest } from '@/lib/api/contracts';
import { UserPicker } from './user-picker';

type Props = {
  open: boolean;
  person: Personnel;
  piiVisible: boolean;
  onClose: () => void;
  onSaved?: (updated: Personnel) => void;
};

type FormState = {
  full_name: string;
  position: string;
  group_id: string;
  phone: string;
  email: string;
  hired_at: string;
  user_id: number | null;
};

function toFormState(person: Personnel): FormState {
  return {
    full_name: person.full_name ?? '',
    position: person.position ?? '',
    group_id: person.group_id ?? '',
    phone: person.phone ?? '',
    email: person.email ?? '',
    hired_at: person.hired_at ?? '',
    user_id: person.user_id ?? null,
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
  return {
    full_name: form.full_name,
    position: form.position,
    group_id: form.group_id.trim() || null,
    phone: form.phone.trim() || null,
    email: form.email.trim() || null,
    hired_at: form.hired_at.trim() || null,
    user_id: form.user_id,
  };
}

export function PersonnelEditModal({ open, person, piiVisible, onClose, onSaved }: Props) {
  const [form, setForm] = useState<FormState>(() => toFormState(person));
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [showErrors, setShowErrors] = useState(false);
  const [photoUrl, setPhotoUrl] = useState<string | null>(null);
  const [hasPhoto, setHasPhoto] = useState<boolean>(Boolean(person.photo_ref));
  const [photoBusy, setPhotoBusy] = useState(false);
  const [photoError, setPhotoError] = useState<string | null>(null);
  const photoInputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    if (open) {
      setForm(toFormState(person));
      setSubmitError(null);
      setShowErrors(false);
      setSubmitting(false);
      setPhotoError(null);
      setHasPhoto(Boolean(person.photo_ref));
      setPhotoUrl(null);
      if (person.photo_ref) {
        void getPersonnelPhotoUrl(person.personnel_id).then((res) => {
          if (res) setPhotoUrl(res.url);
        });
      }
    }
  }, [open, person]);

  const onPickPhoto = async (file: File) => {
    if (!file) return;
    setPhotoBusy(true);
    setPhotoError(null);
    try {
      await uploadPersonnelPhoto(person.personnel_id, file);
      setHasPhoto(true);
      const res = await getPersonnelPhotoUrl(person.personnel_id);
      if (res) setPhotoUrl(res.url);
    } catch (err) {
      setPhotoError(err instanceof Error ? err.message : 'Ошибка загрузки фото');
    } finally {
      setPhotoBusy(false);
      if (photoInputRef.current) photoInputRef.current.value = '';
    }
  };

  const onDeletePhoto = async () => {
    setPhotoBusy(true);
    setPhotoError(null);
    try {
      await deletePersonnelPhoto(person.personnel_id);
      setHasPhoto(false);
      setPhotoUrl(null);
    } catch (err) {
      setPhotoError(err instanceof Error ? err.message : 'Ошибка удаления фото');
    } finally {
      setPhotoBusy(false);
    }
  };

  const initial = formToInitialRequest(person);
  const next = formToNextRequest(form);
  const patch = buildPersonnelPatch(initial, next);
  const errors: PersonnelValidationError[] = validatePersonnelUpdate(next);

  const errorByField = (field: PersonnelValidationError['field']) =>
    showErrors ? errors.find((e) => e.field === field)?.message : undefined;

  const canSubmit =
    Object.keys(patch).length > 0 && errors.length === 0 && !submitting;

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
        <div className="personnel-photo" style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 12 }}>
          <div
            aria-label="Фото сотрудника"
            style={{
              width: 72,
              height: 72,
              borderRadius: '50%',
              background: 'var(--surface-muted, #f1f5f9)',
              border: '1px solid var(--border, #d0d5dd)',
              overflow: 'hidden',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              flexShrink: 0,
            }}
          >
            {photoUrl ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={photoUrl} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
            ) : (
              <span style={{ fontSize: 22, color: 'var(--text-muted, #94a3b8)' }}>
                {(person.full_name || '?').slice(0, 1).toUpperCase()}
              </span>
            )}
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6, flex: 1 }}>
            <div style={{ display: 'flex', gap: 8 }}>
              <button
                type="button"
                className="btn-outline"
                onClick={() => photoInputRef.current?.click()}
                disabled={photoBusy}
              >
                {photoBusy ? 'Загружаю…' : hasPhoto ? 'Заменить фото' : 'Загрузить фото'}
              </button>
              {hasPhoto ? (
                <button
                  type="button"
                  className="btn-outline"
                  onClick={() => void onDeletePhoto()}
                  disabled={photoBusy}
                >
                  Удалить
                </button>
              ) : null}
            </div>
            <input
              ref={photoInputRef}
              type="file"
              accept="image/jpeg,image/png,image/webp"
              style={{ display: 'none' }}
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) void onPickPhoto(f);
              }}
            />
            <span className="task-create-form__hint">JPG/PNG/WebP, до 5 МБ. Хранится в MinIO.</span>
            {photoError ? (
              <span className="task-create-form__error" role="alert">{photoError}</span>
            ) : null}
          </div>
        </div>

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
                <span className="task-create-form__label">Auth-пользователь</span>
                <UserPicker
                  value={form.user_id}
                  onChange={(userId) => setForm({ ...form, user_id: userId })}
                  placeholder="не привязан"
                />
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
