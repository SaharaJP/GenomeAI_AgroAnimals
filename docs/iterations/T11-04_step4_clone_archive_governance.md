# T11-04 — What-If 2.0: clone/archive + governance flag

## Что добавлено

1) **Клонирование сценариев**: из существующего сценария создаётся новый `draft`, копируются параметры и `data_version`, сохраняется ссылка `cloned_from_scenario_id`.
2) **Архивация сценариев**: директор/админ переводит сценарий в `archived`. Архивный сценарий нельзя редактировать/утверждать и нельзя генерировать по нему PDF отчёт.
3) **Governance-флаг для PDF** (опционально): в `configs/economics/economics_v1.yaml` добавлен `governance.require_approval_for_report_pdf`.
   - По умолчанию `false` (не ломаем MVP+).
   - Если `true`, то PDF можно генерировать только для сценария со статусом `approved`.

## RBAC

Новые permissions:
- `whatif.scenarios.clone`
- `whatif.scenarios.archive`

Дефолты:
- Zootech/Operator: могут `clone`, не могут `archive`.
- Director/Admin: могут `clone` и `archive`.

## Аудит

Добавлены audit actions:
- `whatif_scenario.clone`
- `whatif_scenario.archive`

## Версионирование

PDF отчёт расширен метаданными управления (status/approved/archive/cloned_from) в `report_meta.json`.
