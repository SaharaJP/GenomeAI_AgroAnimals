# T1-04 — подготовка (до получения точной постановки)

Дата: 2026-01-15

## Что уже проверено
- Репозиторий успешно распакован из архива `genomeai_agroanimals_MVP_plus_T0_04_final.zip`.
- Юнит‑тесты проходят: `pytest` (26 passed).

## Карта проекта (для команды)
- `src/genomeai/` — offline-core (пайплайны ingestion→QC→features→train→score→fact_pack→report).
- `web_cabinet/` — web-cabinet (FastAPI UI/эндпоинты), не считает, а дергает ядро.
- `configs/` — конфиги маппинга/контрактов/таргет‑модулей.
- `db/` — DDL/миграции (если включены в текущей версии).
- `scripts/` — smoke/утилиты запуска.

## Принятые допущения (пока нет ТЗ T1-04)
- T1-04 относится к развитию (target) и не ломает MVP сценарий UC‑1.
- Любые изменения будут:
  - с отдельными тестами;
  - с сохранением сквозных версий (data_version, qc_run, model_version, scoring_run, report_version, decision_log);
  - с разделением offline-core/web-cabinet.

## TODO после получения постановки T1-04
- Зафиксировать требования и acceptance criteria в `docs/iterations/T1-04.md`.
- Реализовать минимальный инкремент + тесты + smoke-команды.
