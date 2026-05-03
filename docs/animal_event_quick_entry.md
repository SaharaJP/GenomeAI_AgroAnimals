# T20-02 — Быстрый ввод событий по одному животному

Что добавлено:
- quick entry use-cases в `core.operational.quick_entry`
- append-only сценарии: `create`, `confirm`, `close_episode`, `comment`
- человекочитаемая validation/error model: `AnimalEventQuickEntryError`
- web/mobile entry surfaces используют эти use-cases через backend contracts и append-only semantics
- отдельные audit actions: `animal_event.quick_entry.*`

Ключевые правила:
- UI не считает бизнес-логику: он вызывает core use-cases
- подтверждение и закрытие не меняют исходное событие, а добавляют новый append-only record
- для confirm/close используется связь `linked_object_type='animal_event'` + `linked_object_id=<target_event_id>`
- ошибки показываются пользователю в человекочитаемом виде, без silent-fix

Короткие сценарии:
1. **Добавить событие** — выбрать тип, дату/время, при необходимости комментарий/reason code
2. **Подтвердить событие** — выбрать исходное событие и записать confirm как отдельный append-only шаг
3. **Закрыть эпизод** — выбрать событие/эпизод и записать закрытие как отдельный append-only шаг
4. **Добавить комментарий** — оставить comment с optional linkage на событие

RBAC:
- просмотр: `animal_events.view` (есть fallback на `drilldown.view`)
- запись: `animal_events.write`
- подтверждение: `animal_events.confirm`
- закрытие: `animal_events.close`

Роли по умолчанию:
- `Admin`, `Zootech`, `Vet`, `Operator`: quick entry поддерживается в новом web/mobile contour где это разрешено
- `Viewer`: только просмотр истории
