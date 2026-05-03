# T32-09 — Android offline / sync / conflict / audit model

## Цель

Сделать cowside-действия временно исполнимыми offline, а последующую синхронизацию — объяснимой, audit-safe и воспроизводимой без превращения mobile state во второй источник правды.

## Базовые принципы

- Сервер остаётся **единственным источником истины**.
- Android хранит только локальные drafts, queued envelopes и incident diagnostics.
- Silent conflict resolution запрещён.
- Любой replay обязан сохранять linkage к:
  - объекту,
  - версии объекта,
  - task/worklist ownership,
  - handover,
  - assistant-linked action,
  - server audit ack.

## Что добавляется на этом шаге

### 1. Local persistence baseline

В Android-проект добавлен явный слой локального хранения sync-данных:

- `sync_queue`
- `sync_incidents`

Room-сущности и DAO:

- `SyncQueueEntity`
- `SyncIncidentEntity`
- `SyncQueueDao`
- `SyncIncidentDao`
- `MobileSyncDatabase`

Это фиксирует, что offline execution не живёт в неявном UI state.

### 2. Queue / conflict / replay model

Pure-Kotlin слой синхронизации:

- `OfflineSyncLocalStore`
- `InMemoryOfflineSyncLocalStore`
- `SyncTransport`
- `OfflineSyncService`
- `SyncDiagnostics`

Он задаёт воспроизводимую модель:

1. capture offline
2. store envelope locally
3. mark ready for replay
4. replay through transport
5. получить либо `serverAck`, либо retryable failure, либо conflict, либо terminal failure
6. записать incident diagnostics

## Offline-safe capture

Поддерживаются только backend-approved действия:

- `QuickEventEntry`
- `TaskCompletion`
- `ShiftHandover`
- `FeedbackSubmission`
- `AssistantLinkedAction`

Все они проходят через один и тот же `SyncEnvelope`.

## Linkage semantics

Чтобы не терять traceability, envelope и payload должны нести:

- `ObjectVersionLinkage`
- `TaskWorklistOwnershipLinkage`
- `HandoverLinkage`
- `SyncLineage`
- `SyncAuditSemantics`
- `SyncIdempotency`

Это позволяет одинаково трактовать действие и на клиенте, и на backend.

## Retry policy

Retry допускается только для:

- `RetryableNetwork`
- `RetryableServer`

Политика:

- `MAX_RETRY_ATTEMPTS = 5`
- exponential backoff
- после превышения лимита — terminal failure

Retryable сбои формируют incident diagnostics категории `sync_retry`.

## Conflict model

Conflict не может закрываться silent merge.

При конфликте:

- envelope переводится в `AwaitingConflictResolution`
- записывается `SyncConflictRecord`
- создаётся `SyncIncidentDiagnostic` категории `sync_conflict`

Режимы разрешения:

- `ClientReplayRequired`
- `ManualReviewRequired`
- `RejectSilentMerge`

Для `FeedbackSubmission` режим фиксирован как `RejectSilentMerge`.

## Audit-safe replay

Успешный replay обязан завершаться `SyncServerAck`, который содержит:

- `serverAuditId`
- `acceptedAtIso`
- `serverObjectVersion`
- `serverTaskOwnerUserId`
- `serverHandoverId`

До получения `serverAuditId` мобильный клиент не считает действие финально принятым.

## Mobile-ready incident diagnostics

Для расследования sync failures клиент хранит `SyncIncidentDiagnostic` со следующими полями:

- severity
- category
- reasonCode
- summary
- occurredAtIso
- retryEligible
- linkage к объекту / ownership / handover

Это делает сбои пригодными для support/pilot/readiness разборов.

## Проверяемость

Поведение проверяется:

- pytest-тестами на docs/files/policies
- pure-Kotlin smoke без Android emulator
- сценариями:
  - success with audit ack
  - retryable failure with backoff
  - conflict without silent merge
  - duplicate idempotency key rejection

## Чего здесь нет намеренно

На этом шаге не реализуются:

- доменная бизнес-логика на клиенте
- локальный merge бизнес-объектов
- silent reconciliation через UI эвристики
- превращение mobile store во второй источник правды

## Acceptance focus

Полевые действия считаются реализованными корректно, если:

- их можно временно capture offline,
- они попадают в локальную очередь и incidents store,
- replay не теряет linkage и audit semantics,
- конфликт не скрывается,
- traceability сохраняется до server audit ack.
