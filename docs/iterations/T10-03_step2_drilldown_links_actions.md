# T10-03 Step2 — Drill-down 3.0: переходы из KPI/alerts + быстрые действия

## Что добавлено

1) **Deep-link из KPI (Director Summary) → KPI Drilldown v3**
   - Кнопка `🔎 Drill-down` в KPI-тайлах открывает `pages/2_KPI_Drilldown.py`.
   - Параметры передаются через `st.session_state`:
     - `kpi_drilldown.data_version`
     - `kpi_drilldown.kpi_run_id`
     - `kpi_drilldown.asof_date`
     - `kpi_drilldown.kpi_id`
   - Внизу Director Summary добавлен селектор KPI → кнопка «Открыть KPI Drill-down».

2) **KPI Drilldown v3: prefill виджетов из session_state**
   - В `pages/2_KPI_Drilldown.py` всем параметрам добавлены ключи (key=...), поэтому значения могут устанавливаться из других страниц.

3) **Alert Center v2: drill-down и быстрые действия**
   - Кнопка «Открыть объект (drill-down)» ведёт в профиль животного или группы.
   - Кнопка «Открыть отчёт по report_version» ведёт на страницу `pages/10_Regular_Reports.py`.
   - Экспандер «Создать задачу по алерту» создаёт `tasks_v1` запись, связывает с `related_alert`.
   - Экспандер «Подтвердить рекомендацию (Decision Log)» пишет запись в `decision_log_v2`.

4) **Animal Profile / Group Profile: связи entity ↔ task ↔ decision**
   - В профилях показаны связанные задачи (`tasks_v1`) и решения (`decision_log_v2`).
   - В профиле животного добавлена форма «Подтвердить рекомендацию (из алерта)».

5) **Audit log (web.db)**
   - Добавлены audit-события для: `drilldown.open`, `report.open`, `tasks.create`, `decision.append`, `alert.acknowledge`, `alert.resolve`.

## Как проверить

```bash
pytest -q tests/test_t10_03_drilldown_basics.py \
  tests/test_t10_01_streamlit_pages_compile.py \
  tests/test_t10_01_pages_have_guards.py \
  tests/web/test_tasks_v1.py \
  tests/web/test_decision_log_v2.py \
  tests/web/test_rbac_audit.py

streamlit run streamlit_app/0_Home_v3.py
```

Проверки в UI:

- Director Summary → KPI tile → `🔎 Drill-down` → KPI Drilldown → Group Profile → Animal Profile.
- Alert Center → выбрать алерт → `Открыть объект`.
- Alert Center → `Создать задачу` → затем Animal/Group Profile → «Связанные задачи».
- Alert Center/Animal Profile → «Подтвердить рекомендацию» → Decision Log v2.

