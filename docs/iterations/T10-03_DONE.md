# T10-03 — Drill-down 3.0: KPI → группа → животное (DONE)

## Цели итерации

1) Сделать сквозной drill‑down из KPI/alerts в профиль группы и профиль животного.
2) Добавить таймлайн событий (repro/health/sensors/milk) и отображение связанных tasks/decisions.
3) Добавить быстрые действия: создать задачу, подтвердить рекомендацию, открыть отчёт по run_id.

## Что реализовано

### Offline-core

- `genomeai.drilldown`:
  - текущая привязка животных к группе (pen) на `asof_date` с учётом `dm_pen_moves`,
  - разбивка KPI по группам и животным (`kpi_breakdown_by_pen`, `kpi_breakdown_by_animal`),
  - unified **таймлайн** по фактам: `milk/sensors/health/repro` (`build_animal_timeline`).

### Web-cabinet (Streamlit)

- KPI Drilldown v3 → переход в Group Profile → переход в Animal Profile.
- Alert Center v2:
  - кнопка «Открыть объект (drill-down)»,
  - «Открыть отчёт» по `report_version` (run_id отчёта),
  - создание задачи по алерту и подтверждение рекомендации (Decision Log v2).
- Animal Profile:
  - таймлайн фактов + overlay задач и решений,
  - быстрые действия: создать задачу, подтвердить рекомендацию, открыть отчёт.
- Group Profile:
  - список животных текущей группы,
  - связанные задачи и решения с поддержкой алиасов `pen/group`.

### Связи + аудит

- Связи entity↔task↔decision через `object_type/object_id` + trace поля (`data_version`, `qc_run`, `model_version`, `scoring_run`, `report_version`).
- Критичные действия пишутся в `audit_log` (web.db): drilldown.open, report.open, tasks.create, decision.append, alert.acknowledge, alert.resolve.

> Примечание по RBAC: подтверждение рекомендации доступно, если у пользователя есть **хотя бы одно** из:
> `recommendations.confirm` / `decisions.write` / `decisionlog.write` (важно для роли Director).

## Как проверить

```bash
cd <repo>
export PYTHONPATH=src

pytest -q \
  tests/test_t10_03_drilldown_basics.py \
  tests/test_t10_03_nav_utils.py \
  tests/test_t10_03_streamlit_audit_action.py \
  tests/test_t10_03_timeline_build_df.py \
  tests/test_t10_03_streamlit_rbac_actions.py \
  tests/test_t10_01_streamlit_pages_compile.py \
  tests/test_t10_01_pages_have_guards.py \
  tests/web/test_t10_03_entity_aliases.py

streamlit run streamlit_app/0_Home_v3.py
```

UI smoke:
- Director Summary → KPI tile «🔎 Drill-down» → KPI Drilldown v3 → Group Profile → Animal Profile.
- Alert Center v2 → «Открыть объект» → Animal/Group Profile.
- Alert Center v2 → «Создать задачу по алерту» → профили показывают связанную задачу.
- Alert Center v2 / Animal Profile → «Подтвердить рекомендацию» → запись в Decision Log v2.
