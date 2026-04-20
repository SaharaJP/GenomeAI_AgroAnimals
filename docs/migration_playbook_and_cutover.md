# Migration playbook and cutover

## Что делает

T26-05 добавляет формализованный путь перехода на GenomeAI без day-1 irreversible cutover:

- import readiness
- formal migration verification
- parallel run evidence
- user training sign-off
- cutover preview
- rollback readiness
- incident-ready support diagnostics

## Что создаётся

Для каждого `data_version` создаётся versioned playbook run:

`artifacts/<data_version>/migration_playbook/<playbook_run>/`

Артефакты:

- `checklist_rows.csv`
- `checklist_report.xlsx`
- `cutover_report.md`
- `incident_diagnostics.json`
- `playbook_manifest.json`
- `*_backup_preview.zip` (если включено)
- `*_support_bundle.zip` (если включено)

## Логика

Playbook не выполняет необратимый cutover. Он формирует preview-only readiness report и собирает bounded evidence для команды внедрения.

Шаги чеклиста:

1. Data import and mapping readiness
2. Formal migration verification
3. Parallel run and freshness scope
4. User training and field readiness
5. Rollback criteria and support readiness
6. Cutover preview

## Статусы шагов

- `ready`
- `warning`
- `manual_action`
- `blocked`
- `preview_ready`

## Overall readiness

- `ready_for_cutover_preview`
- `manual_review`
- `blocked`

## Ограничения

- Это не universal reconciliation engine.
- Это не irreversible cutover executor.
- Backup/support bundle создаются как evidence and rollback preparation, а не как подтверждение успешного перехода сами по себе.
- Freshness и trusted scope наследуют ограничения batch legacy exports и latest verification evidence.
