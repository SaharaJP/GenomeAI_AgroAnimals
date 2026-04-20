# Batch entry workflows

T20-03 добавляет безопасный массовый ввод operational events по списку животных без дублирования batch-логики в UI.

## Что входит
- core use-cases:
  - `preview_animal_event_batch_use_case(...)`
  - `commit_animal_event_batch_use_case(...)`
- dry-run preview до commit
- per-row validation summary
- append-only commit с общим `request_id` / `batch_preview_id`
- audit actions:
  - `animal_event.batch_entry.preview`
  - `animal_event.batch_entry.commit`

## Поддержанные batch-сценарии
- `assign_check` — назначить проверку
- `mark_insemination` — отметить осеменение
- `move_to_group` — перевести в группу
- `close_status` — закрыть статус
- `schedule_follow_up` — назначить follow-up

## Поведение preview
Preview ничего не пишет в `animal_events_v1`.
Он:
- нормализует список животных,
- проверяет обязательные поля action-параметров,
- формирует per-row статус `valid/invalid`,
- возвращает digest/preview_id для обязательного следующего commit.

Batch нельзя применить без предварительного preview.

## Поведение commit
Commit:
- принимает только preview-объект типа `animal_event_batch_preview_v1`,
- проверяет digest preview,
- для каждой valid-row пишет отдельный append-only event,
- invalid rows не записывает,
- runtime conflicts помечает как `conflict`,
- возвращает понятную итоговую summary.

## Почему это rollback-friendly
В append-only модели rollback массового действия как mass-update не допускается.
Поэтому каждая строка batch commit:
- либо записывается как отдельное событие,
- либо остаётся неприменённой (`invalid/conflict`).

Это сохраняет историю воспроизводимой и безопасной для аудита.

## Web UI
Сценарий batch entry теперь относится к target web frontend и должен вызываться через backend contracts без UI-specific бизнес-логики.
