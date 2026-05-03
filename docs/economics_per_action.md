# Economics per action

T27-03 вводит bounded decision-level economics layer для operational execution.

## Что делает

Показывает economics per action / decision / worklist item:
- expected ROI
- action cost
- expected loss/gain
- cost of delay
- explainable factors
- formulas / assumptions
- versioned economics inputs

## Что НЕ делает

- Не заменяет strategic what-if.
- Не строит «магическую» экономику без формул.
- Не принимает автоматическое необратимое решение вместо пользователя.

## Поддержанные practical paths

- `culling_review` → использует `cow_value_culling_v1`
- `milk_quality` → использует `milk_quality_scc_cockpit_v1`
- `reproduction` → bounded repro-action economics
- `vet` / `health_follow_up` → bounded health-action economics
- `movement` / `manager_review` / `data_cleanup` → bounded generic operational heuristic

## Формулы

Все формулы и assumptions выводятся на странице `pages/65_Economics_Per_Action.py`.

Ключевое разграничение:
- strategic economics / what-if остаётся в director-level surfaces;
- operational action economics показывает, зачем делать конкретное действие сейчас.

## Интеграции

- Daily Worklists → economics preview + `Open action economics`
- Mobile Worklists → `Open economics`
- Decisions → economics context отображается, если decision записан с economics metadata
- Cow value / culling и Milk quality / SCC остаются source engines для специальных operational domains
