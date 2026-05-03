# T11-03 — Step 4: ROI diff-in-diff для групп (pen/site)

## Что добавлено

1) В `genomeai.roi_attribution` добавлен diff-in-diff для `object_type=pen/site` на базе `unit_economics_group_daily`.
2) Добавлен конфиг `roi.group_did` в `configs/economics/roi_attribution_v1.yaml`:
   - `pen_control_scope`: site|farm (контрольные pen в том же scope)
   - `site_control_scope`: farm
   - пороги `min_control_groups`, `min_coverage` и правила исключения контролей по действиям.
3) Логика выставляет те же флаги качества (`NO_CONTROL_GROUP`, `LOW_CONTROL_COVERAGE`) и делает fallback на before/after при недостатке контроля.

## Методика

Для pen/site при `roi.method=diff_in_diff`:
- treated_delta = avg_after(treated) - avg_before(treated)
- control_delta = avg_after(controls) - avg_before(controls)
- effect_used = (treated_delta - control_delta) * window_days

Контроль подбирается на `action_date` и фильтруется от действий в общем окне (до/после), чтобы снизить смещение.

## Дисклеймеры

- Это attribution, а не доказанная причинность.
- На уровне групп сезонность/изменение состава животных может влиять сильнее; интерпретация ROI требует контекста.
