# ROI attribution (T11-03)

Витрина «ROI от решений/закрытых задач» — оценка эффекта по марже из `unit_economics`.

**Важно:** это *attribution* (корреляционная оценка), а не доказанная причинность.

## Источники действий

1) Legacy offline: `artifacts/<data_version>/decisions/decision_log.csv` (фильтр по `decision` ∈ accepted).
2) Web (опционально): `web.db` (sqlite) — таблицы:
   - `decision_log_v2` (append-only)
   - `tasks_v1` (append-only, учитываются `status='done'`)

## Методика

Для каждого действия с датой `action_date`:
- Берём ряд `margin_rub` (маржа) из:
  - `unit_economics_animal_daily` для `object_type=animal`
  - `unit_economics_group_daily` для `object_type=pen/site/farm`.
- Считаем два окна длиной `window_days`:
  - **before**: дни перед действием
  - **after**: дни после действия
- Оцениваем эффект:
  - `delta_margin_per_day = after_avg - before_avg`
  - `delta_margin_window = delta_margin_per_day * window_days`

Дополнительно (если включено в конфиге `roi.method=diff_in_diff`):
- **diff-in-diff** для `object_type=animal`: контрольные животные подбираются по scope (pen/site/farm) и эффект корректируется на изменение контроля.
- **diff-in-diff** для `object_type=pen/site`: контрольные группы подбираются по `roi.group_did` (pen→другие pen в site/farm, site→другие site в farm).

Стоимость действия (`cost_rub`) вычисляется best-effort по простому маппингу `action_type` → параметр `economics_v2.cost_models`.

## Выходные файлы

`artifacts/<data_version>/roi/<roi_run>/`
- `roi_actions.csv` — ROI по каждому действию
- `roi_summary.csv` — агрегаты по месяцам/типам действий
- `roi_quality.csv` — сводка качества/покрытия по флагам (для UI)
- `roi_action_series.csv` — (опц.) ряд вокруг действия (treated vs control mean), чтобы UI мог строить графики без вычислений
- `roi_action_components.csv` — (опц.) разложение эффекта по компонентам unit_economics (доход/расходы/маржа)
- `manifest.json` — параметры, источники, дисклеймеры

Также копия в Target run layout:
`artifacts/<data_version>/runs/<roi_run>/roi/*`

## Дисклеймеры/ограничения

- Показатели могут быть смещены из-за сезонности, изменений кормления, состава групп, здоровья и др. факторов.
- При неполном покрытии дат в окнах before/after качество помечается `LOW_COVERAGE`.
- При недостатке контроля для diff-in-diff ставятся `NO_CONTROL_GROUP`/`LOW_CONTROL_COVERAGE` и выполняется fallback на before/after.
- Стоимость действий может быть `0` (тип не распознан) — ставится флаг `COST_UNKNOWN`, `roi_ratio` не рассчитывается.
- Если для объекта нет строк в unit_economics на нужные даты — ставится `MISSING_SERIES`.

## Дополнительно: baseline matching (опционально)

Чтобы снизить selection bias при выборе контроля, можно включить `roi.control.matching` / `roi.group_did.matching`.
Алгоритм: контрольные объекты сортируются по близости базовой маржи `before_margin_avg` к treated и берётся `top_k`.
