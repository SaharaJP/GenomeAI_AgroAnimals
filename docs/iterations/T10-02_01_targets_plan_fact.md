# T10-02 (шаг 1/4): цели/пороги KPI + план‑факт витрина

Что добавили:

1) Конфиг целей/порогов KPI: `configs/kpi/kpi_targets_v1.yaml`.
2) Offline-core модуль `genomeai.kpi_targets`:
   - загрузка целей с поддержкой override-хранилища Web Cabinet (`web_storage/config_overrides`),
   - расчёт витрины план‑факт (actual vs target) со статусами OK/WARN/ALERT/NO_TARGET.
3) Дашборд директора (`genomeai.dashboard_director.export_director_summary`) теперь сохраняет:
   - `dashboards/director_summary/kpi_plan_fact.csv`,
   - лист `plan_fact` в `director_summary.xlsx`,
   - lineage в `run_manifest.json` (targets_config + override_dir).
4) Streamlit страница Director Summary показывает таблицу план‑факт и использует тот же offline-core расчёт.
5) Экспорт snapshot логируется в audit log (START/OK/ERROR) через `web.db`.

Проверка:

```bash
pytest -q tests/test_t10_02_kpi_targets_plan_fact.py -q
pytest -q tests/test_director_dashboard.py -q
```

Как переопределить цели через Web Cabinet:

1) Открыть Web Cabinet → Configs.
2) Загрузить файл под путём `configs/kpi/kpi_targets_v1.yaml`.
3) В Streamlit Director Summary указать `targets config rel path=configs/kpi/kpi_targets_v1.yaml` (по умолчанию так).

Следующий шаг (T10-02, шаг 2): тренды 7/30/90, топ‑отклонения и объяснения с ссылками на источники/run_id.
