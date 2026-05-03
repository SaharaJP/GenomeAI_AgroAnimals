# T10-03 Step4 — Drill-down 3.0: алиасы entity + тесты связей

## Что добавлено

1) **Единая нормализация entity** (`web_cabinet.entities`):
   - `normalize_object_type()` — канонизация (`pen` → `group`, `cow` → `animal`).
   - `expand_object_types()` — список алиасов для поиска связанных объектов.

2) **Связи entity ↔ task/decision** устойчивы к алиасам:
   - `web_cabinet.tasks_v1.list_tasks_for_object()` выбирает задачи по `object_type IN (...)`.
   - `web_cabinet.decision_log_v2.list_decisions_for_object()` аналогично.
   - `Group Profile` использует эти функции, поэтому показывает и старые записи (`pen`), и новые (`group`).

3) **Alert Center v2** теперь сохраняет задачи/решения с нормализованным `object_type`.

4) **Тесты**: добавлен web-тест на видимость `pen`-сущностей в `group`-профиле.

## Как проверить

```bash
pytest -q tests/test_t10_03_drilldown_basics.py \
  tests/test_t10_03_nav_utils.py \
  tests/test_t10_01_streamlit_pages_compile.py \
  tests/web/test_t10_03_entity_aliases.py

streamlit run streamlit_app/0_Home_v3.py
```

UI smoke:
- Alert Center v2 → алерт с object_type=pen → «Создать задачу» → Group Profile → «Связанные задачи».
- Если в web.db уже были записи с `object_type=pen`, они также должны отображаться в Group Profile.
