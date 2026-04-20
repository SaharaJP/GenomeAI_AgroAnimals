# Backup/restore drill

T17-07 добавляет автоматизированный drill критичного recovery-path:

1. создать backup текущего runtime state;
2. восстановить его в отдельный restore-root;
3. проверить checksums/manifest через existing restore path;
4. сравнить selected artifacts и ключевые sqlite tables;
5. записать audit-событие `backup.drill` и сформировать JSON/Markdown report.

## Что сравнивается

По умолчанию policy `configs/ops/backup_restore_drill_v1.yaml` включает:

- selected artifact files по glob:
  - `**/manifest.json`
  - `**/report*.json`, `**/report*.md`
  - `**/fact_pack*.json`, `**/fact_pack*.md`
  - `**/decision*.json`
  - `**/tasks*.json`
- sqlite tables:
  - `audit_log`
  - `jobs`
  - `decision_log_v2`
  - `tasks_v1`

Для `audit_log` игнорируются ожидаемые drill/restore delta actions (`backup.restore`, `backup.drill*`), чтобы сравнение ловило реальные регрессии состояния, а не служебные записи самого drill.

## CLI

```bash
PYTHONPATH=src python -m genomeai.cli restore-drill \
  --project-root . \
  --artifacts artifacts \
  --web-storage web_cabinet/storage \
  --db-path web_cabinet/storage/web.db \
  --report-root artifacts/restore_drills_manual
```

Успешный запуск печатает:

- `RESTORE_DRILL_OK`
- `drill_id=...`
- `backup_zip=...`
- `report_json=...`
- `report_md=...`
- `artifact_mismatches=0`
- `db_mismatches=0`

## Отчёты

Каждый запуск пишет в `artifacts/restore_drills/<drill_id>/`:

- `restore_drill_report.json` — machine-readable report;
- `restore_drill_report.md` — человекочитаемая сводка;
- `backup/<drill_id>.zip` — backup archive, использованный в drill.

Restore snapshot по умолчанию удаляется после успешного сравнения и сохраняется только при failure (`keep_restore_snapshot_on_failure: true`). Это уменьшает накопление мусора, но оставляет материалы для диагностики инцидента.

## Audit

В исходную sqlite БД пишется событие:

- `backup.drill` со статусом `OK` или `ERROR`.

`after` payload включает:

- `backup_zip`
- `report_json`
- `report_md`
- `restore_verified_files`
- `restore_total_files`
- `artifact_mismatches`
- `db_mismatches`
- `restore_smoke_ok`

## Локальный runbook

```bash
PYTHONPATH=src pytest -q tests/test_t17_07_backup_restore_drill.py
bash scripts/run_backup_restore_drill.sh artifacts/restore_drills_local
```

Проверить затем:

- что последняя запись `backup.drill` появилась в `audit_log`;
- что `restore_drill_report.json` содержит `summary.ok=true`;
- что `artifact_mismatches=0` и `db_mismatches=0`.

## CI / nightly

Добавлен workflow `.github/workflows/backup_restore_drill.yml`.

Nightly path:

1. checkout + install;
2. `web_cabinet.smoke` поднимает синтетическое runtime state;
3. `scripts/run_backup_restore_drill.sh` запускает backup→restore drill;
4. reports публикуются как CI artifact.

Это intentionally отдельный gate, а не часть бизнес-smoke, чтобы recovery diagnostics не смешивались с основной логикой пайплайнов.
