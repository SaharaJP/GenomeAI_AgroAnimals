'use client';

import { useEffect, useMemo, useState } from 'react';
import { Card } from '@/components/ui/card';
import { EmptyState } from '@/components/ui/empty-state';
import { ExplainabilityBlock } from '@/components/ui/explainability-block';
import { Modal } from '@/components/ui/modal';
import {
  fetchPermissionMatrix,
  patchPermissionOverride,
  rolesFromMatrix,
  type IamMatrixResponse,
  type IamOverrideEffect,
} from '@/lib/api/iam';
import { pathLabels } from '@/lib/navigation';
import { useAuth } from '@/components/auth/auth-provider';

type PendingChange = {
  role: string;
  permission: string;
  actionTitle: string;
  actionKey: string;
  currentlyAllowed: boolean;
};

export function IamMatrix() {
  const [matrix, setMatrix] = useState<IamMatrixResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [pending, setPending] = useState<PendingChange | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [toast, setToast] = useState<string | null>(null);

  const auth = useAuth() as { me: { user?: { permissions?: string[] } } | null };
  const canManage = (auth.me?.user?.permissions ?? []).includes('admin.manage');

  const load = async (): Promise<void> => {
    try {
      const data = await fetchPermissionMatrix();
      setMatrix(data);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось загрузить IAM-матрицу');
    }
  };

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    void fetchPermissionMatrix()
      .then((data) => {
        if (active) setMatrix(data);
      })
      .catch((err) => {
        if (active) setError(err instanceof Error ? err.message : 'Не удалось загрузить IAM-матрицу');
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  const roles = useMemo(() => (matrix ? rolesFromMatrix(matrix) : []), [matrix]);

  function showToast(msg: string) {
    setToast(msg);
    setTimeout(() => setToast(null), 4000);
  }

  function openConfirm(role: string, action: { title: string; key: string; permissions: string[] }) {
    if (!canManage) return;
    if (action.permissions.length === 0) return;
    const primaryPermission = action.permissions[0]!;
    const currentlyAllowed = Boolean(matrix?.actions.find((a) => a.key === action.key)?.roles[role]);
    setPending({
      role,
      permission: primaryPermission,
      actionTitle: action.title,
      actionKey: action.key,
      currentlyAllowed,
    });
  }

  async function confirmChange() {
    if (!pending) return;
    setSubmitting(true);
    const effect: IamOverrideEffect = pending.currentlyAllowed ? 'revoke' : 'grant';
    try {
      const resp = await patchPermissionOverride(pending.role, pending.permission, effect);
      const verb = effect === 'grant' ? 'выдан' : 'отозван';
      showToast(
        `Permission «${pending.permission}» ${verb} для роли «${pending.role}». Effective: ${resp.effective_permissions_count}. Применится после следующего входа.`,
      );
      setPending(null);
      await load();
    } catch (err) {
      showToast(err instanceof Error ? err.message : 'Ошибка PATCH override');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="grid">
      <div className="topbar">
        <div>
          <h1 className="page-title">{pathLabels['/admin/iam'] || 'IAM-матрица'}</h1>
          <p className="page-subtitle">
            Привязка ролей к действиям и permissions. Источник истины — `configs/security/permission_matrix_v1.yaml`
            (CLAUDE.md §6) + DB-overrides поверх (table `role_permissions_overrides_v1`). Admin с permission
            `admin.manage` может редактировать через 2-click confirm.
          </p>
        </div>
      </div>

      {error ? (
        <Card>
          <p className="error-text">{error}</p>
        </Card>
      ) : null}

      <Card>
        <h3 className="card-title">
          Permissions × Roles
          {matrix ? <span className="iam-matrix__version"> · версия {matrix.version}</span> : null}
        </h3>
        {loading ? (
          <p className="card-subtitle">Загрузка матрицы…</p>
        ) : !matrix || matrix.actions.length === 0 ? (
          <EmptyState
            title="Матрица пуста"
            description="Endpoint /api/admin/permission-matrix вернул пустые actions. Проверьте, что permission_matrix_v1.yaml зарегистрирован."
          />
        ) : (
          <div className="iam-matrix__scroll">
            <table className="iam-matrix__table">
              <thead>
                <tr>
                  <th scope="col" className="iam-matrix__action-col">
                    Действие
                  </th>
                  {roles.map((role) => (
                    <th key={role} scope="col" className="iam-matrix__role-col">
                      {role}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {matrix.actions.map((action) => (
                  <tr key={action.key}>
                    <th scope="row" className="iam-matrix__action-cell">
                      <div className="iam-matrix__action-title">{action.title}</div>
                      <div className="iam-matrix__action-key">{action.key}</div>
                      {action.permissions.length > 0 ? (
                        <ul className="iam-matrix__perm-list">
                          {action.permissions.map((p) => (
                            <li key={p}>
                              <code>{p}</code>
                            </li>
                          ))}
                        </ul>
                      ) : null}
                    </th>
                    {roles.map((role) => {
                      const allowed = Boolean(action.roles?.[role]);
                      const interactive = canManage && action.permissions.length > 0;
                      return (
                        <td key={role} className="iam-matrix__cell">
                          <input
                            type="checkbox"
                            checked={allowed}
                            disabled={!interactive}
                            readOnly={!interactive}
                            onChange={() => interactive && openConfirm(role, action)}
                            aria-label={`Роль ${role} имеет действие ${action.title}: ${allowed ? 'да' : 'нет'}`}
                            style={{ cursor: interactive ? 'pointer' : 'default' }}
                          />
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <p className="card-subtitle iam-matrix__readonly-hint">
          {canManage
            ? 'Клик по чекбоксу открывает confirm-диалог (2-click safety). Изменение применяется к новым логинам.'
            : 'Только просмотр. Для редактирования нужно permission admin.manage.'}
        </p>
      </Card>

      <ExplainabilityBlock
        title="Контракт матрицы"
        reasons={[
          'Строки = логические действия (action.key, action.title) с одной или несколькими permissions.',
          'Колонки = роли из политики безопасности (src/core/security/policy.py).',
          'Чек = role даёт permissions этого действия. Effective = YAML + DB-overrides (table role_permissions_overrides_v1).',
          'Чтение матрицы не пишет audit; редактирование пишет (action=iam.permission.{grant|revoke|clear}, before/after).',
          'Backend hard-guard: revoke admin.manage у Admin отклоняется 400 iam.lock_out_protected (защита от lock-out).',
          'Изменения вступают в силу только после следующего входа: текущие auth-сессии кешируют permissions (R4).',
        ]}
      />

      <Modal
        open={pending !== null}
        onClose={() => !submitting && setPending(null)}
        title="Подтвердите изменение IAM"
      >
        {pending ? (
          <div className="iam-confirm">
            <p style={{ marginBottom: 12 }}>
              {pending.currentlyAllowed ? 'Отозвать' : 'Выдать'} permission{' '}
              <code>{pending.permission}</code> {pending.currentlyAllowed ? 'у роли' : 'для роли'}{' '}
              <strong>{pending.role}</strong>?
            </p>
            <p style={{ marginBottom: 12, fontSize: 13, color: 'var(--text-muted, #667085)' }}>
              Действие: «{pending.actionTitle}» <code>({pending.actionKey})</code>
            </p>
            <div
              role="alert"
              style={{
                padding: '8px 12px',
                borderLeft: '3px solid var(--warning, #f59e0b)',
                background: 'var(--surface-muted, #fff8e6)',
                fontSize: 13,
                marginBottom: 16,
              }}
            >
              <strong>⚠ Внимание.</strong> Изменение применится только при следующем входе пользователей этой
              роли. Текущие активные сессии продолжат использовать кэшированные permissions до logout/refresh
              (R4 в risks-регистре). Изменение пишется в audit-log.
            </div>
            <div className="task-create-form__actions" style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
              <button type="button" className="btn-outline" onClick={() => setPending(null)} disabled={submitting}>
                Отмена
              </button>
              <button
                type="button"
                className={pending.currentlyAllowed ? 'btn-danger' : 'btn-primary-teal'}
                onClick={() => void confirmChange()}
                disabled={submitting}
              >
                {submitting
                  ? 'Применяю…'
                  : pending.currentlyAllowed
                    ? 'Отозвать (revoke)'
                    : 'Выдать (grant)'}
              </button>
            </div>
          </div>
        ) : null}
      </Modal>

      {toast ? (
        <div className="toast" role="status" aria-live="polite">
          {toast}
        </div>
      ) : null}
    </div>
  );
}
