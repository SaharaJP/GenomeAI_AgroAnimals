# T11-03 step 6 — ROI детали: ряды вокруг действия + компонентная декомпозиция

## Что добавлено

1) **Offline-core**: опциональные detail-артефакты для ROI (чтобы web-cabinet мог делать drill-down без вычислений):
   - `roi_action_series.csv` — дневной ряд вокруг `action_date` (treated и среднее по control), по метрикам `margin/total_cost/revenue_total`.
   - `roi_action_components.csv` — разложение эффекта по компонентам `unit_economics` (доходы/расходы/маржа) в формате до/после и (если применимо) diff-in-diff.
   - В `roi_actions.csv` добавлен флаг `details_available`.

2) Конфиг `configs/economics/roi_attribution_v1.yaml` расширен секцией `roi.outputs`:
   - `action_series: true|false`
   - `action_components: true|false`
   - `details_max_actions: N` — ограничение на количество действий, для которых сохраняются детализации (по умолчанию 500 последних по дате).

3) **Web-cabinet**: страница **ROI панель (T11-03)** показывает детали по выбранному `action_id`:
   - таблица компонент эффекта
   - график ряда вокруг действия
   - экспорт detail CSV (если присутствуют)

## Проверка

CLI:
1) Сгенерируйте unit economics и ROI:
   - `genomeai economics-v2 ...`
   - `genomeai unit-economics ...`
   - `genomeai roi --artifacts-root artifacts --data-version dv_...`
2) Убедитесь, что появились файлы:
   - `artifacts/<dv>/roi/<roi_run>/roi_action_series.csv`
   - `artifacts/<dv>/roi/<roi_run>/roi_action_components.csv`

UI:
1) Откройте **ROI панель (T11-03)**.
2) В блоке **Детали действия** выберите `action_id`.
3) Убедитесь, что отображаются таблица компонент и график.

## Примечания

Detail-артефакты — это данные для визуализации; **атрибуция и качество** определяются так же, как в `roi_actions.csv`.