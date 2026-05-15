'use client';

import { useEffect, useState } from 'react';
import { EmptyState } from '@/components/ui/empty-state';
import { Modal } from '@/components/ui/modal';
import { apiFetch } from '@/lib/api/client';
import { useAuth } from '@/components/auth/auth-provider';
import { hasPermission } from '@/lib/api/contracts';
import { deletePersonnel } from '@/lib/api/personnel';
import { PersonnelEditModal } from '@/components/team/personnel-edit-modal';
import type { ListResponse, Personnel, WorklistItem } from '@/lib/api/contracts';

type TasksBucket = { items: WorklistItem[]; total: number };

function useWorklists(
  query: string | null,
  reloadKey: number = 0,
): { data: TasksBucket | null; error: string | null } {
  const [data, setData] = useState<TasksBucket | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!query) {
      setData(null);
      setError(null);
      return;
    }
    let active = true;
    setError(null);
    void apiFetch<ListResponse<WorklistItem>>(query)
      .then((res) => {
        if (active) {
          setData({ items: res.items || [], total: res.total ?? (res.items?.length || 0) });
        }
      })
      .catch((err) => {
        if (active) setError(err instanceof Error ? err.message : 'Ошибка загрузки задач');
      });
    return () => {
      active = false;
    };
  }, [query, reloadKey]);

  return { data, error };
}

function WorklistMiniList({ items }: { items: WorklistItem[] }) {
  if (items.length === 0) {
    return <EmptyState title="Нет задач" description="Активных задач для этого фильтра не найдено." />;
  }
  return (
    <ul className="personnel-detail__tasks">
      {items.map((task) => (
        <li key={task.task_id} className="personnel-detail__task">
          <span className={`personnel-detail__status personnel-detail__status--${task.status}`}>{task.status}</span>
          <span className="personnel-detail__task-title">{task.title}</span>
          {task.due_at ? <time className="personnel-detail__task-due">{task.due_at}</time> : null}
        </li>
      ))}
    </ul>
  );
}

export function PersonnelDetail({
  person,
  piiVisible,
  onClose,
  onChanged,
  onDeleted,
  worklistsReloadKey = 0,
}: {
  person: Personnel;
  piiVisible: boolean;
  onClose: () => void;
  onChanged?: (updated: Personnel) => void;
  onDeleted?: () => void;
  worklistsReloadKey?: number;
}) {
  const { me } = useAuth();
  const canManage = hasPermission(me, 'personnel.manage');
  const [editOpen, setEditOpen] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  // Personal tasks: only meaningful when the personnel record is linked to an auth user.
  const personalQuery = person.user_id != null ? `/worklists?owner_user_id=${person.user_id}` : null;
  const groupQuery = person.group_id ? `/worklists?assignee_team=${encodeURIComponent(person.group_id)}` : null;

  const personal = useWorklists(personalQuery, worklistsReloadKey);
  const group = useWorklists(groupQuery, worklistsReloadKey);

  // ESC to close — skip while a child modal owns the keyboard
  useEffect(() => {
    if (editOpen || confirmOpen) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [onClose, editOpen, confirmOpen]);

  const handleDelete = async () => {
    setDeleting(true);
    setDeleteError(null);
    try {
      await deletePersonnel(person.personnel_id);
      setConfirmOpen(false);
      onDeleted?.();
    } catch (err) {
      setDeleteError(err instanceof Error ? err.message : 'Ошибка удаления');
    } finally {
      setDeleting(false);
    }
  };

  return (
    <div className="drawer-backdrop" onClick={onClose} role="presentation">
      <aside
        className="drawer personnel-detail"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label={`Карточка сотрудника: ${person.full_name}`}
      >
        <header className="drawer-header">
          <div>
            <h2 className="card-title">{person.full_name}</h2>
            <p className="card-subtitle">{person.position}</p>
          </div>
          <div className="personnel-detail__actions">
            {canManage ? (
              <>
                <button
                  type="button"
                  className="btn-outline personnel-detail__action"
                  onClick={() => setEditOpen(true)}
                >
                  Изменить
                </button>
                <button
                  type="button"
                  className="btn-outline personnel-detail__action personnel-detail__action--danger"
                  onClick={() => setConfirmOpen(true)}
                >
                  Удалить
                </button>
              </>
            ) : null}
            <button type="button" className="an-dialog-close" onClick={onClose} aria-label="Закрыть карточку">
              ×
            </button>
          </div>
        </header>
        <div className="drawer-body personnel-detail__body">
          <section aria-labelledby="personnel-detail-info">
            <h3 id="personnel-detail-info" className="personnel-detail__section-title">
              Информация
            </h3>
            <dl className="card-dl">
              <div>
                <dt>Группа</dt>
                <dd>{person.group_id || '—'}</dd>
              </div>
              <div>
                <dt>Учётная запись</dt>
                <dd>{person.user_id != null ? `user_id=${person.user_id}` : '— (не привязан)'}</dd>
              </div>
              {piiVisible && person.phone ? (
                <div>
                  <dt>Телефон</dt>
                  <dd>
                    <a href={`tel:${person.phone}`}>{person.phone}</a>
                  </dd>
                </div>
              ) : null}
              {piiVisible && person.email ? (
                <div>
                  <dt>Email</dt>
                  <dd>
                    <a href={`mailto:${person.email}`}>{person.email}</a>
                  </dd>
                </div>
              ) : null}
              {piiVisible && person.hired_at ? (
                <div>
                  <dt>Принят</dt>
                  <dd>{person.hired_at}</dd>
                </div>
              ) : null}
            </dl>
            {!piiVisible ? (
              <p className="personnel-surface__hint" role="status">
                Контактные данные скрыты — нет права personnel.read_pii.
              </p>
            ) : null}
          </section>

          <section aria-labelledby="personnel-detail-personal">
            <h3 id="personnel-detail-personal" className="personnel-detail__section-title">
              Личные задачи{personal.data ? ` (${personal.data.total})` : ''}
            </h3>
            {person.user_id == null ? (
              <EmptyState
                title="Учётная запись не привязана"
                description="Сотруднику не сопоставлен auth-аккаунт (user_id=null). Личные задачи появятся после привязки в админке."
              />
            ) : personal.error ? (
              <EmptyState title="Не удалось загрузить" description={personal.error} />
            ) : personal.data === null ? (
              <p className="card-subtitle">Загрузка…</p>
            ) : (
              <WorklistMiniList items={personal.data.items} />
            )}
          </section>

          <section aria-labelledby="personnel-detail-group">
            <h3 id="personnel-detail-group" className="personnel-detail__section-title">
              Задачи группы{group.data ? ` (${group.data.total})` : ''}
            </h3>
            {!person.group_id ? (
              <EmptyState
                title="Сотрудник без группы"
                description="Назначьте сотрудника в группу, чтобы видеть командные задачи."
              />
            ) : group.error ? (
              <EmptyState title="Не удалось загрузить" description={group.error} />
            ) : group.data === null ? (
              <p className="card-subtitle">Загрузка…</p>
            ) : (
              <WorklistMiniList items={group.data.items} />
            )}
          </section>
        </div>
      </aside>
      <PersonnelEditModal
        open={editOpen}
        person={person}
        piiVisible={piiVisible}
        onClose={() => setEditOpen(false)}
        onSaved={(updated) => onChanged?.(updated)}
      />
      <Modal open={confirmOpen} onClose={() => (deleting ? undefined : setConfirmOpen(false))} title="Удалить сотрудника?">
        <div className="task-create-form">
          <p>
            Удаление сотрудника <strong>{person.full_name}</strong> ({person.position}) необратимо. Запись будет
            физически удалена из базы. Связанные задачи (если они привязаны через user_id) останутся существовать
            под прежним owner_user_id.
          </p>
          {deleteError ? (
            <p className="task-create-form__error" role="alert">
              {deleteError}
            </p>
          ) : null}
          <div className="task-create-form__actions">
            <button
              type="button"
              className="btn-outline"
              onClick={() => setConfirmOpen(false)}
              disabled={deleting}
            >
              Отмена
            </button>
            <button
              type="button"
              className="personnel-detail__action--danger personnel-detail__action"
              onClick={handleDelete}
              disabled={deleting}
            >
              {deleting ? 'Удаляем…' : 'Удалить'}
            </button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
