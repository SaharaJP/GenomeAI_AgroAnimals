# T22-05 — repro ↔ mating integration

Цель итерации — перестать держать reproduction cockpit/worklists и mating plan как две disconnected surfaces.

Что сделано:
- добавлен core snapshot `build_repro_mating_integration_snapshot(...)`;
- строится **pending breeding decision queue** поверх `reproduction worklists` + latest `mating_plan` + latest `pedigree constraints`;
- UI не считает pedigree/mating ограничения: все explainable constraints приходят из core;
- decisions пишутся через общий `decision_log_v2` и при наличии `worklist_id` автоматически линкуются к worklist;
- для blocked/override кейсов можно завести `manager_review` worklist через общий worklist use-case.

## Источники
- `build_reproduction_worklists_snapshot(...)`
- latest `artifacts/<data_version>/mating_plan/<run>/mating_plan.csv`
- latest `artifacts/<data_version>/pedigree/<run>/inbreeding_constraints.csv`
- `dm_bulls.csv` для availability / metadata

## Статусы очереди breeding decision
- `ready_for_decision`
- `decision_recorded`
- `awaiting_timing_window`
- `blocked_no_mating_plan`
- `blocked_inbreeding`
- `blocked_unavailable_bulls`
- `blocked_no_candidates`

## Explainable ограничения
Очередь явно показывает, почему кейс не готов к действию:
- инбридинг (`inbreeding constraints`)
- breeding goals / need-boost из `configs/mating_plan/mating_plan_v1.yaml`
- unavailable bulls
- timing constraints (животное ещё не в окне для breeding decision)

## Linkage / версии
Каждая breeding decision сохраняет:
- `object_type=animal`, `object_id=<animal_id>`
- `data_version`
- `mating_plan_run`
- `pedigree_run`
- `recommendation_id` (`mating_plan:<run>:<animal_id>` when available)
- source facts / constraints summary

## Ограничения
- mating logic целиком не переписывалась;
- страница интеграции использует latest mating/pedigree artifacts best-effort;
- старые решения, записанные только как `object_type=mating_pair`, не всегда можно надёжно связать обратно с animal-level queue.
