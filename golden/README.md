# Golden set для `verify_refactor`

`golden/` хранит **компактные** эталоны для T15-01.

Состав:
- `scenarios/standard/inputs/` — базовый синтетический сценарий.
- `scenarios/qc_issues/inputs/` — сценарий с QC warnings, но без блокировки полного пайплайна.
- `scenarios/*/snapshot/` — нормализованные эталоны для сравнения (`qc`, `score`, `report`, `fact_pack`, `decision_log`, `tasks`, `audit`).

Что **не** кладём в golden:
- большие бинарные артефакты (`.xlsx/.docx/.pdf`) целиком;
- абсолютные пути и timestamp-поля;
- случайные идентификаторы задач.

Вместо этого golden хранит:
- нормализованные JSON/CSV snapshot-файлы;
- `artifact_presence.json` с проверкой наличия ключевых бинарных артефактов.

В корне `golden/` дополнительно хранится `manifest.json`:
- список snapshot/input файлов по каждому сценарию;
- `sha256` и размер каждого файла;
- суммарный размер golden для контроля разрастания репозитория.


## Локальный запуск

```bash
pip install -e .
genomeai verify_refactor
# в CLI будет напечатан путь до golden_manifest и verify_report
```

CLI остаётся совместимым, но orchestration запуска вынесен в `src/genomeai/application/refactor_verify.py`; это удерживает `cli.py` тонким адаптером без переноса бизнес-логики в UI/CLI слой. Отдельный compare/report слой вынесен в `src/genomeai/application/refactor_verify_compare.py`.

## Ручное обновление golden

Обновление намеренно сделано **только вручную** и требует явного подтверждения:

```bash
genomeai verify_refactor --update-golden --i-understand-update-golden
```

Обновлять golden нужно только если команда **осознанно** принимает новый baseline поведения.
После обновления обязательно закоммитьте и `golden/manifest.json`, иначе verify_refactor покажет drift самого golden.

- T15-01 refactor note: scenario selection and verify report-root orchestration are now isolated in `src/genomeai/application/refactor_verify_runtime.py`; `src/genomeai/refactor_verify.py` remains a backward-compatible facade.

- T15-01 refactor note: verify result/status payload and CLI rendering are now isolated in `src/genomeai/application/refactor_verify_result.py`; this does not change golden contents or CLI output format.
- T15-01 refactor note: use-case orchestration now reaches legacy `genomeai.refactor_verify` through `src/genomeai/application/refactor_verify_service.py`; golden contents and update/verify semantics are unchanged.

Дополнительно fail-fast исключения (`ValueError`, `FileNotFoundError`, `RuntimeError`) теперь маппятся отдельным helper-слоем `src/genomeai/application/refactor_verify_errors.py` в тот же совместимый статус `VERIFY_REFACTOR_FAILED` с человекочитаемыми полями `action/error_type/error_code/reason`. Успешный вывод `verify_refactor` при этом не изменён.
