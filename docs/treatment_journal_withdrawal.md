# Treatment journal & withdrawal control

T23-02 добавляет единый `treatment journal` поверх runtime DB и legacy `dm_treatments`.

## Что считается source of truth

- **runtime treatment journal**: `treatment_journal_v1`
- **legacy imported treatments**: `dm_treatments.csv` (read-only surface, без записи обратно)
- **withdrawal rules**: `configs/health/withdrawal_rules.yaml`

## Что хранится в runtime journal

- course / status / animal / farm / site / pen
- linked alert / health event / protocol execution / worklist
- treatment type / drug / dose / route / duration
- follow-up due / follow-up status
- withdrawal rule version / withdrawal days / source/calc/effective dates
- source versions / metadata

## Как считается withdrawal

Используется versioned rule-set из `configs/health/withdrawal_rules.yaml`.

Правило:

- `last_admin_date = end_date if present else start_date`
- `withdrawal_end_date_calc = last_admin_date + withdrawal_days_rule`
- `withdrawal_end_date_effective = source override if present else calc`
- `withdrawal_active_asof = effective >= asof_date`

## Что НЕ делаем

- не ставим диагноз автоматически
- не делаем clinical engine
- не храним critical treatment state только в Streamlit
- не переписываем существующие report/economics flows

## Workflow

1. старт курса лечения -> runtime row + audit
2. обновление курса -> recompute withdrawal + audit
3. завершение курса -> final status / optional follow-up + audit
4. active withdrawal surfaces -> animal/group/farm level tables

## Linkage

- `linked_alert_id`
- `linked_health_event_id`
- `linked_protocol_execution_id`
- `linked_worklist_id`
- `data_version` + `source_versions_json`

Это нужно, чтобы withdrawal ограничения были воспроизводимы и видны в операционных экранах.
