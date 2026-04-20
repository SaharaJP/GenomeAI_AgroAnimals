# T11-03 — Step 3: ROI (diff-in-diff) + качество данных

## Что добавлено

1) В offline-core (genomeai.roi_attribution) добавлен метод attribution `diff_in_diff` (difference-in-differences) для `object_type=animal`.
2) Добавлены поля качества/метаданных в `roi_actions.csv`:
   - `method`, `coverage_before/after`, `control_*`, `delta_margin_window_used`, `roi_ratio_used`.
3) Витрина `roi_summary.csv` теперь агрегирует эффекты **и по raw, и по used** (`delta_margin_window_sum` vs `delta_margin_window_used_sum`) и хранит `method`.
4) UI обновлён: ROI-панель и профили показывают `used` эффект и метод.

## Методика

- `before_after`: (avg_after - avg_before) * window_days.
- `diff_in_diff` (animal):
  - treated_delta = avg_after(treated) - avg_before(treated)
  - control_delta = avg_after(controls) - avg_before(controls)
  - effect_used = (treated_delta - control_delta) * window_days

Контроль подбирается на `action_date` по scope (`pen` по умолчанию) и фильтруется от действий в окне.

## Дисклеймеры

- Это attribution, а не доказанная причинность.
- Качество зависит от полноты unit_economics и корректности логов решений/задач.

