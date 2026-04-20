# T11-03 step 5 — ROI quality breakdown + baseline matching (optional)

## Что добавлено

1) В offline-core добавлен файл `roi_quality.csv` — агрегаты по `quality_flag/method/object_type`:
   - количество действий
   - суммарный эффект (raw/used)
   - суммарная стоимость
   - среднее покрытие `coverage_before/coverage_after`
   - среднее `control_n_effective` (если применимо)

2) В `roi_actions.csv` добавлено поле `quality_reasons` (человекочитаемые причины флагов) и расширены флаги:
   - `COST_UNKNOWN` — не удалось сопоставить стоимость по cost_models
   - `MISSING_SERIES` — нет рядов unit_economics для объекта

3) Опциональный baseline matching для контроля (по близости `before_margin_avg`):
   - `roi.control.matching.enabled/top_k`
   - `roi.group_did.matching.enabled/top_k`
   По умолчанию выключено.

4) В web-cabinet ROI панель показывает качество из `roi_quality.csv`, добавлены колонки качества и экспорт CSV.

## Проверка

- CLI (создаст `roi_quality.csv`):
  - `genomeai roi --artifacts-root artifacts --data-version dv_demo`

- UI:
  - Страница `ROI панель (T11-03)`
  - Проверьте блок **Качество attribution** и экспорт.

## Примечания

Это attribution; даже с matching причинность не доказана.
