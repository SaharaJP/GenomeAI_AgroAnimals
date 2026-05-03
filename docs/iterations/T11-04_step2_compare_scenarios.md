# T11-04 (step2) — What‑If 2.0: сравнение 2–3 сценариев

## Цель шага
Добавить сравнение 2–3 сохранённых сценариев what-if с базой (multipliers=1) и вывод результатов в UI.

## Что сделано
- В **offline-core** добавлена функция `genomeai.economics_whatif.compare_whatif_scenarios(...)`, которая:
  - запускает `run_economics_whatif` для базы и выбранных сценариев (до 3);
  - считает итоговые метрики (выручка/затраты/маржа/маржинальность) из `summary_farm.csv`;
  - возвращает таблицу сравнения + deltas vs base.
- В **web-cabinet (Streamlit)** добавлен блок "Сравнение 2–3 сценариев":
  - выбор 2–3 сценариев;
  - проверка совместимости контекста (data_version/date_from/date_to/cfg_path);
  - запуск сравнения через offline-core (требуется `pipeline.run`);
  - отображение таблицы и кнопки скачивания xlsx по каждому run;
  - best-effort сохранение `last_economics_run` в сценарии.
- Audit:
  - фиксируется действие `whatif_scenario.compare`;
  - фиксируется `whatif_scenario.run` при обновлении `last_economics_run`.

## Проверка
```bash
pytest -q
streamlit run streamlit_app/app.py
```

## Ограничения
- Для корректного сравнения сценарии должны иметь одинаковые `data_version/date_from/date_to/cfg_path`.
- Пока сравнение агрегируется на уровне всего `summary_farm` (итоги по всем фермам), без drilldown по фермам/группам.
