# RBAC + Audit Log (Target) — T0-05

## Roles
- **Admin**: полный доступ, управление конфигами, просмотр audit.
- **Director**: просмотр KPI/drill-down, экспорт, подтверждение рекомендаций, закрытие алертов, просмотр audit.
- **Zootech**: просмотр KPI/drill-down, загрузки, запуск расчётов (ingest/qc/train/score/report/pack), экспорт, подтверждение рекомендаций, закрытие алертов, решения.
- **Vet**: просмотр KPI/drill-down, экспорт, закрытие алертов, решения.
- **Operator**: загрузки, запуск расчётов, экспорт, решения.
- **Viewer**: только просмотр KPI/drill-down и скачивание готовых артефактов.

## Permission catalog
- `kpi.view`
- `drilldown.view`
- `upload.create`
- `pipeline.run`
- `export.download`
- `alerts.close`
- `recommendations.confirm`
- `decisions.write`
- `configs.manage`
- `audit.view`

## Role → permissions (default)
| Role | kpi.view | drilldown.view | upload.create | pipeline.run | export.download | alerts.close | recs.confirm | decisions.write | configs.manage | audit.view |
|---|---|---|---|---|---|---|---|---|---|---|
| Admin | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Director | ✅ | ✅ |  |  | ✅ | ✅ | ✅ | ✅ |  | ✅ |
| Zootech | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |  |  |
| Vet | ✅ | ✅ |  |  | ✅ | ✅ |  | ✅ |  |  |
| Operator | ✅ | ✅ | ✅ | ✅ | ✅ |  |  | ✅ |  |  |
| Viewer | ✅ | ✅ |  |  | ✅ |  |  |  |  |  |

> Примечание: матрица может быть переопределена через таблицу `role_permissions` (на tenant).

## Audit log
Audit log — append-only (`audit_log`). **Критические события обязаны фиксироваться**:

### Обязательные события
- `auth.login` (успех/ошибка)
- `auth.logout`
- `pipeline.enqueue` (ingest/qc/train/score/report/pack)
- `export.download` (скачивание любых артефактов)
- `decisions.init`, `decisions.add`
- `configs.upload` (изменение правил/контрактов/маппингов)

### Поля (минимум)
- `ts`, `tenant_id`
- `user_id`, `username`, `role`
- `action`
- `object_type`, `object_id`
- `data_version`, `run_id`
- `before_json`, `after_json` (если применимо)
- `ip`, `user_agent`
- `status`, `error`
- `request_id`

## Где смотреть
- UI: `/audit` (нужен `audit.view`)
- API: `/api/audit`
