# T1-03 — Дашборд зоотехника v2 (продуктивность + группы)

## Назначение

Экран зоотехника предназначен для операционной работы с продуктивностью на уровне животных и групп:

1. Ранжирование животных по результатам скоринга (ML обязателен и применяется в `genomeai score`).
2. Аналитика по contemporary groups (farm_id + calving_year + calving_season + parity) и выбросы.
3. Экспорт списков животных и запись пользовательских решений в decision_log.

UI **ничего не “считает”**: он читает артефакты, полученные в офлайн-ядре.

## Источники данных и lineage

### Вход

* `artifacts/<data_version>/runs/<scoring_run>/scoring/scored_latest.csv` (или legacy `artifacts/<data_version>/scoring/<scoring_run>/scored_latest.csv`)
* `artifacts/<data_version>/runs/<scoring_run>/scoring/group_summary.csv`

Колонки берутся из скоринга (см. `src/genomeai/score.py`):

* ключи: `farm_id`, `animal_id`, `lactation_no` (в MVP lactation_id синтезируется при необходимости)
* скоринг: `y_pred`, `residual`, `index_in_group`, `rank_in_group`, `rank_in_farm`, `confidence`, `action`, `action_reasons`
* группировка: `calving_year`, `calving_season`, `parity` (если доступны)

### Выход

Экспорт snapshot:

* `artifacts/<data_version>/runs/<dash_run>/dashboards/zootech_productivity/zootech_productivity.xlsx`
* `artifacts/<data_version>/runs/<dash_run>/dashboards/zootech_productivity/decision_candidates.xlsx`
* `artifacts/<data_version>/runs/<dash_run>/dashboards/zootech_productivity/dashboard_summary.json`

Decision log (append-only, в корне data_version):

* `artifacts/<data_version>/decisions/decision_log.csv`
* `artifacts/<data_version>/decisions/decision_log.xlsx`
* `artifacts/<data_version>/decisions/decision_log.jsonl`

## Простые правила “выбросов” и explainability (v2)

* Выбросы определяются **детерминированно** на основе `residual`:
  * `residual <= -800` → LOW outlier
  * `residual >= +500` → HIGH outlier

Это не медицинские/ветеринарные диагнозы — только triage для зоотехника.

## RBAC

* Просмотр страницы: требуется `kpi.view` + `drilldown.view`.
* Запись решений: дополнительно требуется `decisions.write`.

## Примеры строк (фрагменты)

### scored_latest.csv

| farm_id | animal_id | lactation_no | y_pred | residual | confidence | action |
|---|---|---:|---:|---:|---|---|
| F001 | A000123 | 2 | 9150.2 | 620.1 | HIGH | PRIORITY |
| F001 | A000777 | 3 | 8020.8 | -910.4 | MEDIUM | CULL_CANDIDATE |

### decision_log.csv

| created_at_utc | user | animal_id | lactation_id | recommendation_type | decision | comment |
|---|---|---|---|---|---|---|
| 2026-01-14T07:00:00+00:00 | zootech1 | A000777 | A000777__3 | CULL_CANDIDATE | ACCEPT | низкая продуктивность 2 сезона |
