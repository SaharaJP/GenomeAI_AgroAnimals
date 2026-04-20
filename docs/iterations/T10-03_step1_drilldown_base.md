# T10-03 Step1 — Drill-down 3.0 (KPI → группа → животное)

Что добавлено в шаге:

1) **Offline-core** модуль `genomeai.drilldown`:
   - текущая привязка животных к группам (pen) на `asof_date` (с учётом `dm_pen_moves`),
   - разбивка выбранного KPI по группам (pen) и по животным,
   - единый **таймлайн событий** животного (milk/sensors/health/repro).

2) **Streamlit (web-cabinet)**:
   - обновлён `KPI Drilldown`: показывает farm-level KPI и разбивку по группам, плюс переход в профиль группы,
   - добавлены страницы `Group Profile` и `Animal Profile` с навигацией через `st.session_state` и `st.switch_page`,
   - в профиле животного: быстрый action **создать задачу** (web.db) + список задач + decision log.

Проверка (локально):

```bash
pytest -q tests/test_t10_03_drilldown_basics.py \
  tests/test_t10_01_streamlit_pages_compile.py \
  tests/test_t10_01_pages_have_guards.py

streamlit run streamlit_app/0_Home_v3.py
```

Ограничения:

- Drill-down сейчас считается on-demand (не влияет на `kpi_long.csv`).
- `asof_date` выбирается пользователем в UI; если не совпадает с KPI-run, значения могут отличаться.
- Быстрые действия "подтвердить рекомендацию" и "открыть отчёт по run_id" будут добавлены в следующем шаге T10-03.
