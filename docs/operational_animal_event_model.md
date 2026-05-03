# Operational animal event model (T20-01)

## Что добавлено
- Введён единый append-only log `animal_events_v1` как core-источник operational истории животного.
- Животное (`animal_id`) зафиксировано как основной operational object, к которому привязываются daily-use события.
- Поддержаны нормализованные типы событий: `heat`, `insemination`, `preg_check`, `calving`, `dry_off`, `treatment`, `cull`, `death`, `pen_move`, `comment`, `manual_note`, `custom_operational_event`.

## Модель записи
Каждое событие хранит:
- ключи: `event_id`, `tenant_id`, `animal_id`, опционально `farm_id`, `site_id`, `lactation_id`;
- время: `event_ts`, `event_date`;
- actor/source: `actor_type`, `actor_user_id`, `actor_username`, `source`, `source_ref`;
- explainability/linkage: `reason_code`, `linked_object_type`, `linked_object_id`, `linked_decision_id`, `linked_task_id`;
- lineage/versioning: `request_id`, `job_id`, `data_version`, `qc_run`, `model_version`, `scoring_run`, `report_version`;
- business payload: `payload_json`;
- schema marker: `schema_version`.

## Append-only и audit linkage
- `animal_events_v1` защищена trigger-ами `trg_animal_events_v1_no_update` и `trg_animal_events_v1_no_delete`.
- Каждая запись через service layer создаёт audit event `animal_event.append`.
- Связь event ↔ audit восстанавливается по:
  - `audit_log.object_type='animal_event'`,
  - `audit_log.object_id=event_id`,
  - общему `request_id` (если он был передан).

## Совместимость
Чтобы не ломать текущие loaders/use-cases/pages, существующие таблицы не заменяются:
- `dm_repro_events`
- `dm_treatments`
- `dm_pen_moves`

Вместо этого в offline-core добавлена нормализация legacy-строк в unified event surface:
- `normalize_legacy_operational_event(source_table=...)`

Это позволяет постепенно переводить profile pages / work cards / quick-entry формы на единый log, не разрывая текущие пайплайны.

## Основные entrypoints
- `core.operational.animal_events.build_animal_event(...)`
- `core.operational.animal_events.append_animal_event(...)`
- `core.operational.animal_events.get_animal_event(...)`
- `core.operational.animal_events.list_animal_events_for_animal(...)`
- `core.operational.animal_events.normalize_legacy_operational_event(...)`

## Проверки в тестах
- bootstrap БД создаёт таблицу и append-only trigger-ы;
- update/delete запрещены;
- linked objects / task / decision / versions не теряются;
- audit linkage создаётся автоматически;
- legacy `dm_repro_events` / `dm_treatments` / `dm_pen_moves` нормализуются без ломки текущих загрузчиков.
