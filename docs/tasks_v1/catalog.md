# Tasks v1 catalog

Каталог `configs/tasks_v1/catalog.yaml` задаёт правила, какие типы алертов (`alerts_v2.alert_type`) порождают какие задачи.

Поля правила:
- `task_type` — тип задачи (строка)
- `domain` — домен задачи для Workflow 2.0 (health/repro/data/qc/econ)
- `title` — заголовок
- `priority` — 1..5 (1 — высокий)
- `due_days` — дедлайн в днях, если у алерта нет `deadline`

Дополнительно (опционально):
- `sla_hours` — SLA в часах (если указано — используется для расчёта `due_at`, когда нет `deadline` и `due_days`)

В v1 используется только блок `from_alerts`.


См. также: `docs/tasks_v1/workflow_v2.md` (SLA, назначение, метрики).
