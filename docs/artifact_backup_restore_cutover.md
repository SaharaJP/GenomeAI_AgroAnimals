# T34-05 — Artifact storage / backup / restore / support bundle cutover to adult production path

Статус шага: `partially_proven`.

## Что сделано

### 1. Support bundle приведён к adult runtime contour
`build_support_bundle()` теперь собирает не только inventory/runtime-state, но и явные adult runtime diagnostics:

- `diagnostics/runtime_storage_summary.json`
- `diagnostics/runtime_state_summary.json`
- `diagnostics/auth_diagnostics.json`
- `diagnostics/queue_runtime_summary.json`
- `diagnostics/backup_metadata.json`
- `diagnostics/artifact_integrity_summary.json`

Также bundle теперь подхватывает raw maintenance metadata, если она уже записана в artifact storage:

- `maintenance/latest_backup_metadata.json`
- `maintenance/latest_restore_metadata.json`

`diagnostics/web_db_summary.json` по-прежнему включается только на `sqlite` compat path и больше не считается production maintenance path для adult contour.

### 2. Явно разведены три слоя хранения
В adult maintenance path теперь различаются:

- Postgres runtime persistence
- Redis transient / broker state
- artifact/file/object storage

Backup metadata и restore metadata описывают именно эту модель, а не legacy `web.db`-oriented path.

### 3. Добавлены runnable verification scripts
Новые скрипты:

- `scripts/verify_adult_backup_set.py`
- `scripts/verify_adult_restore_set.py`

Они проверяют:

- backup created
- required components present
- restore metadata recorded
- post-restore smoke status captured
- key artifacts доступны после restore

### 4. Обновлены adult ops scripts
Обновлены:

- `deploy/adult/ops/collect_support_bundle.sh`
- `deploy/adult/ops/backup_host.sh`
- `deploy/adult/ops/restore_host.sh`

Изменения:

- support bundle в adult profile больше не тащит `--db-path /runtime/web_storage/web.db` как production default
- backup manifest теперь фиксирует `runtime_storage_backend=postgres`, `queue_backend=redis`, `artifact_storage_mode=file_or_object_storage`
- backup/restore metadata зеркалятся в `artifacts/system/maintenance/`, чтобы support bundle видел их из runtime contour
- restore path фиксирует `post_restore_smoke_ok`

### 5. Добавлены maintenance artifacts
Новый SQL-файл:

- `deploy/adult/ops/diagnostic_sql/backup_restore_checks.sql`

В нём:

- runtime entity counts
- recent operational lineage
- recent privileged / maintenance audit rows

### 6. Добавлена artifact integrity summary
Новый summary собирает:

- количество `dv_*`
- количество canonical/report/manifests
- latest support bundle
- latest backup
- sha256 примеры последних manifest-файлов

Это не заменяет content verification, но повышает supportability и completeness support bundle.

## Что доказано этим шагом

- support bundle теперь соответствует adult runtime posture, а не legacy `web.db`-centric maintenance path
- backup/restore production path описан runnable scripts и верифицируется отдельными скриптами
- backup/restore metadata теперь доступны внутри runtime artifact contour
- legacy `web.db` path больше не считается production maintenance default для adult contour

## Что ещё не доказано

Пока не доказан live operational proof на реальном adult-like окружении:

- настоящий `pg_dump` / `psql restore` against live PostgreSQL
- настоящий Redis restore / broker continuity proof
- real restored contour boots on deployed stack
- end-to-end proof на реальном compose/k8s contour после restore

Поэтому шаг остаётся `partially_proven`, а не `proven`.
