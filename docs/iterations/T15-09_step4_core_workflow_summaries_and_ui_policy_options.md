# T15-09 step4 — core workflow summaries + UI policy options

Что перенесено в core:
- `core.workflow.summaries.operational_summary_use_case`
- `core.workflow.summaries.tasks_metrics_use_case`
- `core.workflow.summaries.overdue_tasks_use_case`
- policy exports для UI: `alert_status_options`, `task_status_options`, `task_active_status_options`, `task_close_status_options`, `task_priority_options`, `workflow_domain_options`

Что изменено в адаптерах:
- `web_cabinet.app` routes `/api/tasks_v1/metrics` и `/api/tasks_v1/overdue` используют canonical core summary use cases
- mini-web workflow filter options получают status values из `core.workflow`
- Streamlit `home_v3` использует `operational_summary_use_case`
- Streamlit Alert Center / Worklist больше не держат hard-coded workflow status/domain/priority options

Обратная совместимость:
- API payloads и action names сохранены
- free-text reason при закрытии задачи по-прежнему разрешён
- UI reason codes добавлены как подсказка/каталог, а не как жёсткая валидация
