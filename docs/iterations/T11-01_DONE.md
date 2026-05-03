# T11-01 — Экономика 2.0 (DONE)

## Цель
Собрать единые витрины экономики (₽): доходы/расходы/себестоимость/маржа, с прозрачными формулами и страницей в кабинете директора.

## Что реализовано

### Offline-core
- `genomeai economics-v2` рассчитывает витрины:
  - `economics_daily` (farm/site/pen × day)
  - `economics_monthly` (farm/site/pen × month)
- Категории:
  - выручка по молоку
  - корм (as-fed → DM)
  - прочие расходы
  - vet (стоимость на событие лечения)
  - repro (стоимость на событие осеменения)
  - выбраковка/реализация (cull)
- Прозрачность:
  - `formulas_catalog.json`
  - `formula_json`/`sources_json` в строках
- Версионирование:
  - `economics_run` как `run_id`
  - manifest с привязкой к `data_version`.

### Web/Streamlit
- Страница **Экономика 2.0** (Streamlit) с:
  - запуском расчёта (нужны права `pipeline.run`)
  - просмотром daily/monthly
  - расшифровкой формул по выбранной строке
  - экспортом артефактов (нужны права `export.download`) с записью в audit.
- Панель «Экономика (₽)» в **Director Summary** с переходом на Economics 2.0.

### Тесты
- Контрольные примеры в `tests/test_t11_01_economics_v2.py`:
  - проверка конвертации валют и расчёта базовой маржи
  - проверка влияния vet/repro/cull.

## Где лежат артефакты

`artifacts/<data_version>/economics_v2/<economics_run>/`:

- `economics_daily.csv`
- `economics_monthly.csv`
- `formulas_catalog.json`
- `manifest.json`

## Как проверить

```bash
pytest -q

# пример ручного расчёта
genomeai economics-v2 --data-version dv_demo --date-from 2025-01-01 --date-to 2025-01-31

# UI
streamlit run streamlit_app/app.py
```

## Документация

- `docs/target/economics_v2.md`
- `docs/marts/economics_v2.md`
