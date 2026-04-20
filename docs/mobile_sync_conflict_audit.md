# T25-05 — Mobile sync / conflict / audit

Что добавлено:
- bounded server-side sync journal для mobile execution без обещания полноценного offline-first backend;
- статусы `saved / pending_retry / conflict` для mobile действий;
- retry cues на `Mobile worklists` и `Cowside event entry`;
- explainable conflict checks для mobile worklist actions;
- audit linkage для sync states и сохранённых linked ids.

## Что считается safe в этой итерации

Система **не** делает raw client-side state transitions и **не** обещает true offline.

Вместо этого введён server-side `mobile_sync_actions_v1`:
- при transient save problem действие попадает в `pending_retry`;
- при повторной отправке тот же `action_key` не создаёт дубль;
- при state mismatch по worklist пользователь получает bounded `conflict` с explainable причиной.

## Статусы

- `saved` — действие сохранено и связано с `event/worklist/decision` when applicable.
- `pending_retry` — сохранение не завершилось из-за transient problem; payload сохранён для повторной отправки.
- `conflict` — действие отклонено из-за explainable state mismatch или action rejection.

## Где применено

### Mobile worklists
- `Done`
- `+1 day`
- `Comment`

### Cowside event entry
- `Save cowside event`

## Bounded conflict semantics

Для mobile worklist actions конфликт определяется безопасно и объяснимо:
- work item уже закрыт на другом устройстве / другим пользователем;
- snapshot status изменился с момента mobile view.

Это intentionally bounded conflict model. Здесь нет общего optimistic-lock DSL для всех сущностей.

## Audit

Дополнительно пишутся audit события:
- `mobile.sync.saved`
- `mobile.sync.pending_retry`
- `mobile.sync.conflict`

Они **не** подменяют доменные audit события (`worklist.close`, `animal_event.quick_entry.create` и т.д.), а дополняют их transport/sync контекстом.

## Ограничения

- Это не full offline-first execution.
- Если request вообще не дошёл до сервера, server-side outbox не узнает о действии.
- Pending retry сохраняет только те действия, которые уже были приняты серверным слоем и классифицированы как transient failure / retry-needed.
