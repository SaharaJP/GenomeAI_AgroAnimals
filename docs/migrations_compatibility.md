# Schema / runtime migrations compatibility

## Что добавлено в T17-03

В проект введён единый реестр миграций `core.migrations` для трёх классов состояния:

- `web.db` — runtime SQLite состояние web-cabinet;
- `backup_manifest` — архивы backup/restore;
- `pilot_pack` — offline pilot pack архивы для импорта артефактов.

Реестр описывает:

- текущую поддерживаемую версию компонента;
- минимальную поддерживаемую версию (`supported_from`);
- тип компонента (`sqlite`, `sqlite-table`, `artifact-manifest`);
- краткое назначение и политику поддержки.

Формат snapshot реестра:

- `genomeai.migration_registry.v1`

## Политика совместимости

### 1. Web DB / runtime state

`core.infra.web_db.init_db(...)` теперь делает две вещи:

1. **Ранняя валидация** `schema_registry` — если snapshot/БД создан более новой версией проекта, и в `schema_registry` уже записана версия выше поддерживаемой, подъём останавливается сразу с понятной диагностикой.
2. **Синхронизация реестра** после online-migrations — текущие версии `web.db`, `web.db.jobs`, `web.db.audit_log`, `web.db.connector_runs` записываются в таблицу `schema_registry`.

Это не меняет бизнес-поведение, но даёт явный upgrade path и machine-readable точку контроля.

### 2. Backup / restore archives

`genomeai.backup_restore.restore_backup(...)` теперь использует централизованный compatibility helper.

Поддерживаемые форматы:

- `genomeai_backup_v1`
- `genomeai_backup_v2`

Если архив пришёл из **более новой** версии (`format` неизвестен/новее текущей поддержки), restore завершается ранней валидацией с диагностикой:

- какой компонент несовместим;
- какая версия обнаружена;
- какая версия поддерживается;
- что делать дальше.

### 3. Pilot packs / service artifacts

`genomeai.migration_pack_import.import_pilot_pack(...)` теперь валидирует `versions.json` через единый compatibility helper.

Поддерживается:

- `pack_schema_version=1`
- legacy-вариант без `pack_schema_version` (трактуется как `1`)
- alias-поля `dv`, `mv`, `sr`, `rv` для старых snapshot/archive сценариев

Неподдерживаемые случаи ловятся ранней валидацией, без «тихих» поломок позже по ходу импорта.

## Реестр миграций

Канонический код:

- `src/core/migrations/registry.py`
- `src/core/migrations/compatibility.py`

Ключевые текущие версии:

- `web.db = 3`
- `web.db.jobs = 2`
- `web.db.audit_log = 2`
- `web.db.connector_runs = 2`
- `backup_manifest = 2`
- `pilot_pack = 1`

## Supported / unsupported cases

### Supported

- legacy web DB без `schema_registry`, но с поддерживаемыми историческими схемами таблиц;
- backup archive формата `v1` и `v2`;
- pilot pack формата `v1`, включая архивы без `pack_manifest.json`;
- pilot pack с legacy alias-полями (`dv`, `mv`, `sr`, `rv`).

### Explicitly unsupported

- snapshot/DB, где `schema_registry` уже указывает версию **новее**, чем умеет текущий код;
- backup archive формата новее `genomeai_backup_v2`;
- pilot pack с `pack_schema_version > 1`;
- артефакты настолько старые, что они ниже `supported_from` из migration registry.

## Диагностика при несовместимости

Для несовместимости формируется human-readable diagnostic со следующими полями:

- `component`
- `code`
- `message`
- `remediation`
- `current_version`
- `supported_from`
- `detected_version`
- `field`
- `example`

Это позволяет:

- не показывать пользователю сырые traceback в нормальном сценарии;
- сохранять diagnosability для разработчика/оператора;
- централизованно использовать один и тот же подход в DB upgrade и artifact import/restore.

## Как проверить

```bash
PYTHONPATH=src pytest -q \
  tests/test_t17_03_migrations_registry.py \
  tests/test_t17_03_migration_compatibility.py
```

И дополнительно общий gate:

```bash
PYTHONPATH=src pytest -q $(grep -v '^#' ci/pytest_gate.txt | tr '\n' ' ')
```
