# Vet triage queues

## Что добавлено
- core-derived ветеринарные очереди осмотра и follow-up: mastitis, lameness, ketosis, metritis, fresh_cows, retreatment, chronic_review;
- severity / confidence / source facts / due action считаются в core;
- materialize в общий worklist слой через dedupe_key;
- completion идёт через общий outcome loop;
- bulk comments пишутся append-only в unified animal events.

## Источники
- `dm_health_events.csv`
- `dm_lactations.csv` для `fresh_cows`
- `treatment_journal_v1` + `dm_treatments.csv` через `build_treatment_journal_snapshot(...)`
- `alerts_v2` для active health alerts

## Принципы
- никакой отдельной UI-only queue engine;
- никакой отдельной disease model beyond current scope;
- queues best-effort и transparent: показывают, почему кейс попал в список.
