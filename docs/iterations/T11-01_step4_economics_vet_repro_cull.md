# T11-01 Step4 — Vet/Repro/Cull (economics_v2)

Цель шага: закрыть категории **вет‑затраты**, **репродукция**, **выбраковка/реализация** в витрине economics_v2, чтобы на синтетике/демо они были видны и влияли на маржу.

## Что добавлено

- Поддержка `dm_cull_events` (best-effort):
  - агрегируем по `pen_id` и `date` через привязку `animal_id -> pen_id` (pen_moves + current_pen_id);
  - считаем `cull_events_n`, `revenue_cull_rub`, `cost_cull_rub`;
  - `revenue_rub/cost_rub` берём из таблицы; если их нет — используем defaults из конфигурации.

- Конфиг (configs/economics/economics_v2.yaml):
  - добавлены/заданы демо‑значения `vet.cost_per_treatment_event_rub`, `repro.insemination_cost_rub`, `cull.revenue_per_head_rub`, `cull.cost_per_head_rub`.

- Фикстуры `data/fixtures/target_v2` расширены второй датой (2025‑01‑10) и событиями vet/repro/cull, чтобы это было видно в UI.

- В UI (страница `Economics v2`) добавлены колонки по выбраковке: `cull_events_n`, `revenue_cull_rub`, `cost_cull_rub`.

## Проверка

- `pytest -q` — включает контрольный пример с vet/repro/cull на дате `2025-01-10`.
- `python -m genomeai.cli economics-v2 ...` — генерирует витрины и манифест.

## Дальше

- При необходимости: расширить модели затрат vet/repro (по типам событий/препаратам) и добавить справочники (unit costs) как отдельные dm_*.
