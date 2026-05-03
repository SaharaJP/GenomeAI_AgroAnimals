# T11-04 Step5 — What-If 2.0: Compare API для web-cabinet

## Цель
Добавить серверный API-эндпоинт для сравнения 2–3 сохранённых what-if сценариев с базовым сценарием (BASE), чтобы UI не реализовывал расчётные формулы и мог запрашивать результаты сравнения через web-cabinet.

## Что сделано
- Добавлен endpoint `POST /api/whatif_compare_v1`.
- Endpoint:
  - принимает `scenario_ids` (2–3) и опциональный `base_context` (data_version/date_from/date_to/cfg_path);
  - валидирует контекст всех сценариев на совпадение;
  - вызывает offline-core `genomeai.economics_whatif.compare_whatif_scenarios`;
  - обновляет `last_economics_run` в `whatif_scenarios_v1` (best-effort);
  - пишет audit: `whatif_scenario.compare` и `whatif_scenario.run`.
- Ответ содержит:
  - `comparison` (таблица BASE + сценарии),
  - `base_economics_run`,
  - `scenario_runs` (по scenario_id),
  - пути `xlsx_base` и `xlsx_by_scenario` для скачивания через `/download`.

## RBAC
- Требуются permissions:
  - `whatif.scenarios.view`
  - `pipeline.run`

## Тесты
- Добавлен `tests/web/test_whatif_compare_v1.py`.
