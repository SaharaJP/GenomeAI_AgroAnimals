# T32-08A — Android offline / sync / conflict contract

## Цель

Формально зафиксировать offline-first контракт Android-клиента так, чтобы event entry, task completion, handover, feedback и assistant-linked actions работали в offline режиме объяснимо, audit-safe и без silent merge.

## Принципы

- Android не содержит бизнес-логики принятия решений.
- Android хранит **только transport/sync semantics**, а сервер остаётся источником истины.
- Любая offline операция обязана иметь:
  - scope (`tenant/farm/site`),
  - audit block,
  - idempotency block,
  - lineage block,
  - status lifecycle,
  - явную conflict policy.
- Silent merge запрещён.
- Conflict resolution не может основываться на неявных UI-допущениях.

## Offline-safe действия

В очередь разрешено ставить только:

- `QuickEventEntry`
- `TaskCompletion`
- `ShiftHandover`
- `FeedbackSubmission`
- `AssistantLinkedAction`

Все остальные действия должны трактоваться как online-only, пока не появится отдельный backend-approved contract.

## Queue model

Ключевая сущность — `SyncEnvelope`.

Она обязана содержать:

- `actionType`
- `scope`
- `payloadJson`
- `audit`
- `idempotency`
- `lineage`
- `precondition`
- `status`
- `attemptCount`
- `nextRetryAtIso`
- `lastFailureClass`
- `conflict`

Явная checked-in схема:

- `specs/jsonschema/android_offline_sync_contract_v1.json`

## Sync lifecycle

Разрешённые статусы:

- `Pending`
- `ReadyToSync`
- `InFlight`
- `AwaitingConflictResolution`
- `Synced`
- `FailedRetryable`
- `FailedTerminal`
- `Cancelled`

Допустимые переходы фиксируются в `SyncLifecyclePolicy`.

Запрещено:

- переводить `Synced` обратно в `Pending`
- скрывать conflict как успешную синхронизацию
- silently drop'ать terminal failures

## Retry policy

Retry разрешён только для:

- `RetryableNetwork`
- `RetryableServer`

Не retry'ятся:

- `Conflict`
- `TerminalValidation`
- `TerminalAuth`
- `Cancelled`

Базовая политика:

- max attempts = 5
- exponential backoff
- задержка ограничена сверху

## Idempotency semantics

Каждый queued action обязан иметь:

- `idempotencyKey`
- `semanticKey`
- `dedupeWindowHours`

Это нужно, чтобы повторная отправка после reconnect/retry не создавала неаудируемые дубли.

Смысл:

- transport retry не должен менять доменный смысл операции;
- backend и mobile одинаково трактуют повторную доставку как тот же action, а не как новый скрытый merge.

## Conflict semantics

Конфликт формализуется как `SyncConflictRecord`.

Он обязан содержать:

- серверную версию объекта,
- серверный статус,
- режим разрешения,
- reason code,
- человекочитаемое summary.

### Conflict modes

- `QuickEventEntry` → `ClientReplayRequired`
- `TaskCompletion` → `ManualReviewRequired`
- `ShiftHandover` → `ManualReviewRequired`
- `FeedbackSubmission` → `RejectSilentMerge`
- `AssistantLinkedAction` → `ManualReviewRequired`

Checked-in policy:

- `configs/mobile/android_sync_conflict_policy_v1.json`

## Audit semantics

Каждая offline операция обязана нести:

- `actorUserId`
- `actorRole`
- `mobileSessionId`
- `deviceId`
- `queuedAtIso`
- `clientObservedAtIso`
- `requiresServerAuditAck = true`

Это означает:

- сервер должен подтвердить audit ingestion;
- мобильный клиент не может считать операцию финально принятой без server audit ack;
- assistant-linked actions и feedback обязаны быть так же трассируемы, как task completion или handover.

## Assistant-linked actions

Android не исполняет assistant logic локально.

Offline допускается только постановка в очередь **assistant-linked action envelope**, который:

- ссылается на `relatedAssistantActionId`,
- имеет idempotency block,
- проходит серверную валидацию/аудит при синхронизации.

## Проверяемость

Контракт считается воспроизводимым, потому что есть:

- checked-in schema
- checked-in conflict policy
- pure-Kotlin sync models/policies
- smoke, который компилирует и исполняет contract-level assertions без Android emulator
- pytest-проверки на docs/schema/policy consistency

## Что не делается на этом шаге

- полноценный sync engine с Room/WorkManager
- background scheduler production-grade уровня
- локальный merge бизнес-объектов
- конфликтное разрешение на базе UI эвристик

## Acceptance focus

Android offline execution и последующая синхронизация считаются корректными, если:

- поведение объяснимо,
- нет silent merges,
- есть audit trail,
- retry и conflict трактуются одинаково мобильным клиентом и backend contract layer.
