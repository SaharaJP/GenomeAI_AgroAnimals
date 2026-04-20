# Backup / Restore 2.0 — step 1

В этом шаге реализован первый инкремент T13-06:
- backup-архив в формате `genomeai_backup_v2`;
- явное включение `artifacts/`, `web_storage/` и sqlite БД (`web.db` + `-wal/-shm`, если есть);
- проверка `sha256` для каждого файла до и после restore;
- легковесный smoke-check после restore.

## Команды

### Создать backup

```bash
python -m genomeai backup \
  --artifacts artifacts \
  --web-storage web_cabinet/storage \
  --db-path web_cabinet/storage/web.db \
  --out artifacts/backups/backup_manual.zip
```

Ожидаемый вывод:
- `BACKUP_OK`
- `backup_zip=...`
- `backup_id=...`
- `file_count=...`

### Выполнить restore с smoke-check

```bash
python -m genomeai restore \
  --backup artifacts/backups/backup_manual.zip \
  --artifacts artifacts \
  --web-storage web_cabinet/storage \
  --db-path web_cabinet/storage/web.db \
  --force \
  --smoke-check
```

Ожидаемый вывод:
- `RESTORE_OK`
- `verified_files=...`
- `total_files=...`
- `restore_smoke_ok=True`

## Что проверяет restore smoke

После восстановления выполняется минимальная проверка среды:
- существуют `artifacts/` и `web_storage/`;
- существует `web.db`;
- в `web_storage/` присутствуют `uploads/`, `logs/`, `config_overrides/`;
- sqlite открывается;
- в БД есть таблицы `users_v2`, `audit_log`, `jobs`;
- если backup содержал `data_version`-каталоги (`dv_*`), они присутствуют после restore.

## Integrity / checksums

`manifest.json` внутри архива содержит `sha256` и размер каждого файла.
Во время restore:
1. архив извлекается во временный каталог;
2. checksums проверяются до установки в целевые пути;
3. после копирования в целевые пути checksums проверяются повторно.

Если есть mismatch, restore завершается ошибкой с человеком читаемой причиной:
- `checksum verification failed before restore`
- `checksum verification failed after restore`

## Audit

Для traceability backup/restore пишут системные audit-события в sqlite, если БД доступна:
- `backup.create`
- `backup.restore`

На этом шаге аудит выполняется в best-effort режиме: отсутствие/повреждение БД не блокирует сам backup, но restore всё равно провалится на smoke-check, если БД не восстанавливается корректно.

## Быстрая end-to-end проверка

```bash
bash scripts/backup_restore_check.sh
```

Скрипт:
1. поднимает smoke-workdir;
2. генерирует demo data через `web_cabinet.smoke`;
3. делает backup;
4. стирает каталоги назначения;
5. выполняет restore + smoke-check.

## Retention / Cleanup policy (T13-06 step 2)

Политика задаётся в `configs/ops/backup_retention_v1.yaml`.

Что поддерживается:
- `backup_archives.keep_last` — сколько последних zip-бэкапов хранить в `artifacts/backups/`.
- `restore_snapshots.keep_last` — сколько служебных каталогов `*_pre_restore_*` хранить после restore с `--force`.
- `data_versions.keep_last` — сколько каталогов `dv_*` хранить в `artifacts/`.

По умолчанию cleanup `dv_*` **выключен**, чтобы не сломать текущие MVP+ сценарии. Для фактического удаления `dv_*` нужно одновременно:
1. включить `data_versions.enabled: true` в YAML;
2. запустить cleanup с флагом `--include-data-versions`.

CLI:

```bash
python -m genomeai backup-cleanup \
  --artifacts artifacts \
  --web-storage web_cabinet/storage \
  --project-root .
```

Это dry-run: показывает кандидатов на удаление, но ничего не удаляет.

Применить cleanup:

```bash
python -m genomeai backup-cleanup \
  --artifacts artifacts \
  --web-storage web_cabinet/storage \
  --project-root . \
  --apply
```

Разрешить cleanup старых `dv_*`:

```bash
python -m genomeai backup-cleanup \
  --artifacts artifacts \
  --web-storage web_cabinet/storage \
  --project-root . \
  --apply \
  --include-data-versions
```

Если в YAML включить `apply_after_backup: true`, retention будет автоматически применяться после успешного `genomeai backup`.
