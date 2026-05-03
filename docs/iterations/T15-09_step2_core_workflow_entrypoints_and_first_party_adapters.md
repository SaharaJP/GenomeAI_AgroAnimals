# T15-09 step 2 — core workflow entrypoints + first-party adapters

## Что сделано
- Добавлен `core.workflow.use_cases.generate_alerts_and_tasks_use_case` для общего orchestration пути: offline alert candidates -> AlertCreate -> upsert_generated_alerts -> auto_create_tasks_from_alerts.
- Добавлен canonical first-party entrypoint `core.workflow.entrypoints.generate_alerts_and_tasks`.
- `web_cabinet.app` теперь использует `core.workflow` напрямую и вызывает единый workflow entrypoint в `/api/alerts_v2/generate`.
- Streamlit pages (`Alert Center`, `Decision Log`, `Worklist`, `Director Summary`, `Mating Plan`, `AI Assistant RAG`, `Animal/Group Profile`, `Report Templates`) переведены на прямые импорты из `core.workflow`.
- `web_cabinet.worker` тоже переведён на `core.workflow` для ops-alert creation.

## Почему это безопасно
- Сигнатуры публичных API не менялись.
- Legacy `web_cabinet.alerts_v2`, `tasks_v1`, `decision_log_v2`, `entities` продолжают существовать как shim/re-export.
- Критичные audit writes остались в adapters и продолжают писать те же действия/объекты.

## Что дальше
- Следующий безопасный шаг T15-09: вынести стандартизацию reason codes / status transitions / SLA metadata в отдельные core policy helpers и перевести remaining workflow views/API endpoints на canonical use-cases вместо ad-hoc orchestration.
