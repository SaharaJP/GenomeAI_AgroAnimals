package com.genomeai.agroanimals.mobile.domain.sync

class OfflineSyncService(
    private val store: OfflineSyncLocalStore,
    private val transport: SyncTransport,
) {
    fun captureOffline(envelope: SyncEnvelope): SyncEnvelope {
        require(SyncQueuePolicy.canQueueOffline(envelope.actionType)) {
            "Action ${envelope.actionType} is not approved for offline queueing"
        }
        require(!store.containsIdempotencyKey(envelope.idempotency.idempotencyKey)) {
            "Duplicate idempotency key: ${envelope.idempotency.idempotencyKey}"
        }
        val pending = envelope.copy(status = SyncStatus.Pending)
        store.enqueue(pending)
        return pending
    }

    fun markReady(envelopeId: String): SyncEnvelope {
        val existing = requireNotNull(store.get(envelopeId)) { "Envelope $envelopeId not found" }
        require(SyncLifecyclePolicy.canTransition(existing.status, SyncStatus.ReadyToSync)) {
            "Illegal transition from ${existing.status} to ReadyToSync"
        }
        val updated = existing.copy(status = SyncStatus.ReadyToSync)
        store.upsert(updated)
        return updated
    }

    fun replayReady(nowIso: String, limit: Int = 50): SyncReplaySummary {
        var synced = 0
        var retryable = 0
        var conflicts = 0
        var terminal = 0
        val batch = store.listReady(nowIso, limit)

        batch.forEach { envelope ->
            val inFlight = envelope.copy(status = SyncStatus.InFlight)
            store.upsert(inFlight)
            when (val result = transport.replay(inFlight)) {
                is SyncTransportResult.Success -> {
                    val syncedEnvelope = inFlight.copy(
                        status = SyncStatus.Synced,
                        lastFailureClass = null,
                        lastFailureCode = null,
                        conflict = null,
                        serverAck = SyncServerAck(
                            serverAuditId = result.serverAuditId,
                            acceptedAtIso = result.acceptedAtIso,
                            serverObjectVersion = result.serverObjectVersion,
                            serverTaskOwnerUserId = result.serverTaskOwnerUserId,
                            serverHandoverId = result.serverHandoverId,
                        ),
                    )
                    store.upsert(syncedEnvelope)
                    synced += 1
                }

                is SyncTransportResult.RetryableFailure -> {
                    val nextAttemptCount = inFlight.attemptCount + 1
                    val shouldRetry = SyncRetryPolicy.shouldRetry(result.failureClass, nextAttemptCount)
                    val nextStatus = SyncLifecyclePolicy.nextStatusAfterFailure(result.failureClass, shouldRetry)
                    val nextRetryAtIso = if (shouldRetry) {
                        "$nowIso+${SyncRetryPolicy.nextRetryDelaySeconds(nextAttemptCount)}s"
                    } else {
                        null
                    }
                    val failedEnvelope = inFlight.copy(
                        status = nextStatus,
                        attemptCount = nextAttemptCount,
                        nextRetryAtIso = nextRetryAtIso,
                        lastFailureClass = result.failureClass,
                        lastFailureCode = result.reasonCode,
                    )
                    store.upsert(failedEnvelope)
                    store.recordIncident(
                        SyncDiagnostics.failureIncident(
                            envelope = failedEnvelope,
                            severity = if (shouldRetry) SyncIncidentSeverity.Warning else SyncIncidentSeverity.Error,
                            category = "sync_retry",
                            reasonCode = result.reasonCode,
                            summary = result.summary,
                            occurredAtIso = nowIso,
                            retryEligible = shouldRetry,
                        )
                    )
                    if (shouldRetry) retryable += 1 else terminal += 1
                }

                is SyncTransportResult.Conflict -> {
                    val conflict = SyncConflictPolicy.buildConflictRecord(
                        actionType = inFlight.actionType,
                        serverObjectVersion = result.serverObjectVersion,
                        serverStatus = result.serverStatus,
                        reasonCode = result.reasonCode,
                        summary = result.summary,
                    )
                    val conflictedEnvelope = inFlight.copy(
                        status = SyncStatus.AwaitingConflictResolution,
                        attemptCount = inFlight.attemptCount + 1,
                        lastFailureClass = SyncFailureClass.Conflict,
                        lastFailureCode = result.reasonCode,
                        conflict = conflict,
                    )
                    store.upsert(conflictedEnvelope)
                    store.recordIncident(SyncDiagnostics.conflictIncident(conflictedEnvelope, conflict, nowIso))
                    conflicts += 1
                }

                is SyncTransportResult.TerminalFailure -> {
                    val failedEnvelope = inFlight.copy(
                        status = SyncStatus.FailedTerminal,
                        attemptCount = inFlight.attemptCount + 1,
                        lastFailureClass = result.failureClass,
                        lastFailureCode = result.reasonCode,
                    )
                    store.upsert(failedEnvelope)
                    store.recordIncident(
                        SyncDiagnostics.failureIncident(
                            envelope = failedEnvelope,
                            severity = SyncIncidentSeverity.Error,
                            category = "sync_terminal",
                            reasonCode = result.reasonCode,
                            summary = result.summary,
                            occurredAtIso = nowIso,
                            retryEligible = false,
                        )
                    )
                    terminal += 1
                }
            }
        }

        return SyncReplaySummary(
            processed = batch.size,
            synced = synced,
            retryableFailures = retryable,
            conflicts = conflicts,
            terminalFailures = terminal,
        )
    }
}
