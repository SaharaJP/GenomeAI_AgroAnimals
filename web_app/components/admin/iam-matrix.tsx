'use client';

import { useEffect, useMemo, useState } from 'react';
import { Card } from '@/components/ui/card';
import { EmptyState } from '@/components/ui/empty-state';
import { ExplainabilityBlock } from '@/components/ui/explainability-block';
import { fetchPermissionMatrix, rolesFromMatrix, type IamMatrixResponse } from '@/lib/api/iam';
import { pathLabels } from '@/lib/navigation';

export function IamMatrix() {
  const [matrix, setMatrix] = useState<IamMatrixResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

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

  return (
    <div className="grid">
      <div className="topbar">
        <div>
          <h1 className="page-title">{pathLabels['/admin/iam'] || 'IAM-матрица'}</h1>
          <p className="page-subtitle">
            Привязка ролей к действиям и permissions. Источник истины — `configs/security/permission_matrix_v1.yaml`
            (CLAUDE.md §6). В этой версии страница работает в режиме просмотра — интерактивное редактирование
            появится после провижининга DB-overrides слоя.
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
                      return (
                        <td key={role} className="iam-matrix__cell">
                          <input
                            type="checkbox"
                            checked={allowed}
                            disabled
                            aria-label={`Роль ${role} имеет действие ${action.title}: ${allowed ? 'да' : 'нет'}`}
                            readOnly
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
          Только просмотр. Редактирование через UI станет доступным после слайса 3 (DB-overrides поверх YAML)
          и слайса 4 (PATCH endpoint + 2-click confirm).
        </p>
      </Card>

      <ExplainabilityBlock
        title="Контракт матрицы"
        reasons={[
          'Строки = логические действия (action.key, action.title) с одной или несколькими permissions.',
          'Колонки = роли из политики безопасности (src/core/security/policy.py).',
          'Чек = role даёт permission'+'s этого действия. Effective permissions = YAML + DB-overrides (когда добавим).',
          'Чтение матрицы не пишет audit; будущее редактирование — пишет (CLAUDE.md §6 «любое привилегированное — audit-logged»).',
        ]}
      />
    </div>
  );
}
