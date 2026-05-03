# Artifact lifecycle hardening (T17-04)

## Что считается runtime/generated outputs

В рамках T17-04 lifecycle policy охватывает только **безопасно очищаемые** семейства:

- `artifacts/_verify_refactor/verify_*` — отчёты и snapshots `verify_refactor`;
- `artifacts/_ci/*` — CI scratch / upload bundles;
- `_tmp/*` — локальные smoke/test/runtime workdirs;
- `artifacts/_archive/*.zip` — runtime archives, собранные CLI-командой;
- `artifacts/support_bundles/*.zip` — support bundles;
- `web_cabinet/storage/logs/*.log` — runtime web logs.

Retention для backup/restore snapshot остаётся централизован в `configs/ops/backup_retention_v1.yaml` и вызывается из `artifact-cleanup`, чтобы не дублировать политику.

## Что нельзя удалять generic cleanup-ом

Generic cleanup **никогда** не трогает:

- `golden/`;
- `installers/` и release-папки;
- manifest-артефакты и release manifests;
- `web_cabinet/storage/web.db`;
- `web_cabinet/storage/uploads/`.

`dv_*` директории по-прежнему считаются чувствительными и могут удаляться только через backup retention policy и только при явном флаге `--include-data-versions`.

## Policy / config

Основная policy хранится в:

- `configs/ops/artifact_lifecycle_v1.yaml`

CLI-команды по умолчанию читают policy из `--project-root`, но можно передать явный `--config`.

## CLI команды

### 1) Dry-run cleanup

```bash
PYTHONPATH=src python -m genomeai.cli artifact-cleanup --project-root .
```

Применить реально:

```bash
PYTHONPATH=src python -m genomeai.cli artifact-cleanup --project-root . --apply
```

### 2) Archive runtime outputs

```bash
PYTHONPATH=src python -m genomeai.cli artifact-archive --project-root . --out artifacts/_archive/runtime_archive_manual.zip
```

Архивировать только delete-candidates:

```bash
PYTHONPATH=src python -m genomeai.cli artifact-archive --project-root . --scope delete_candidates
```

### 3) Support bundle

```bash
PYTHONPATH=src python -m genomeai.cli support-bundle --project-root . --out artifacts/support_bundles/support_bundle_manual.zip
```

Bundle собирается детерминированно:

- фиксированный порядок файлов;
- фиксированные zip timestamps;
- без volatile `generated_at` полей внутри manifest.

## Что попадает в support bundle

- `diagnostics/environment_snapshot.json`;
- `diagnostics/runtime_inventory.json`;
- `diagnostics/web_db_summary.json` (best effort);
- lifecycle/backup policy files;
- latest `verify_report.json/.md`;
- несколько последних `web_cabinet/storage/logs/*.log`.

## Cleanup / retention policy

По умолчанию:

- `verify_reports` — keep last 3;
- `ci_scratch` — keep last 3;
- `_tmp` — keep last 5;
- `runtime_archives` — keep last 5;
- `support_bundles` — keep last 5;
- `web_logs` — keep last 20.

Старые backup zips и restore snapshots очищаются через существующий `backup_retention_v1.yaml`.

## Диагностика и audit

Команды логируют audit events:

- `artifact.cleanup`
- `artifact.archive`
- `artifact.support_bundle`

Если SQLite недоступен, команды продолжают работать best effort, но без audit-записи.
