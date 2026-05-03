package com.genomeai.agroanimals.mobile.contractsmoke

import com.genomeai.agroanimals.mobile.domain.sync.HandoverLinkage
import com.genomeai.agroanimals.mobile.domain.sync.InMemoryOfflineSyncLocalStore
import com.genomeai.agroanimals.mobile.domain.sync.ObjectVersionLinkage
import com.genomeai.agroanimals.mobile.domain.sync.OfflineSyncService
import com.genomeai.agroanimals.mobile.domain.sync.SyncActionType
import com.genomeai.agroanimals.mobile.domain.sync.SyncAuditSemantics
import com.genomeai.agroanimals.mobile.domain.sync.SyncEnvelope
import com.genomeai.agroanimals.mobile.domain.sync.SyncFailureClass
import com.genomeai.agroanimals.mobile.domain.sync.SyncIdempotency
import com.genomeai.agroanimals.mobile.domain.sync.SyncLineage
import com.genomeai.agroanimals.mobile.domain.sync.SyncScope
import com.genomeai.agroanimals.mobile.domain.sync.SyncStatus
import com.genomeai.agroanimals.mobile.domain.sync.SyncTransport
import com.genomeai.agroanimals.mobile.domain.sync.SyncTransportResult
import com.genomeai.agroanimals.mobile.domain.sync.TaskWorklistOwnershipLinkage

private fun assertThat(condition: Boolean, lazyMessage: () -> String) {
    if (!condition) {
        throw IllegalStateException(lazyMessage())
    }
}

private fun testSuccessfulReplayIsAuditSafe() {
    val store = InMemoryOfflineSyncLocalStore()
    val service = OfflineSyncService(store) { envelope ->
        SyncTransportResult.Success(
            serverAuditId = "audit-1",
            acceptedAtIso = "2026-04-13T10:00:05Z",
            serverObjectVersion = "animal-v3",
            serverTaskOwnerUserId = envelope.lineage.ownershipLinkage?.ownerUserId,
            serverHandoverId = envelope.lineage.handoverLinkage?.handoverId,
        )
    }
    val envelope = baseEnvelope(id = "env-1", actionType = SyncActionType.TaskCompletion)
    service.captureOffline(envelope)
    service.markReady("env-1")
    val summary = service.replayReady(nowIso = "2026-04-13T10:00:00Z")
    val saved = store.get("env-1")

    assertThat(summary.synced == 1) { "Expected 1 synced item, got $summary" }
    assertThat(saved?.status == SyncStatus.Synced) { "Expected synced status, got $saved" }
    assertThat(saved?.serverAck?.serverAuditId == "audit-1") { "Expected server audit ack" }
    assertThat(saved?.serverAck?.serverObjectVersion == "animal-v3") { "Expected version linkage ack" }
}

private fun testRetryableFailureProducesIncidentAndBackoff() {
    val store = InMemoryOfflineSyncLocalStore()
    val service = OfflineSyncService(store) {
        SyncTransportResult.RetryableFailure(
            reasonCode = "network_timeout",
            summary = "Gateway timeout",
            failureClass = SyncFailureClass.RetryableNetwork,
        )
    }
    val envelope = baseEnvelope(id = "env-2", actionType = SyncActionType.QuickEventEntry)
    service.captureOffline(envelope)
    service.markReady("env-2")
    val summary = service.replayReady(nowIso = "2026-04-13T11:00:00Z")
    val saved = store.get("env-2")

    assertThat(summary.retryableFailures == 1) { "Expected retryable failure summary" }
    assertThat(saved?.status == SyncStatus.FailedRetryable) { "Expected FailedRetryable status" }
    assertThat(saved?.nextRetryAtIso?.contains("+10s") == true) { "Expected deterministic retry marker" }
    assertThat(store.listIncidents().any { it.reasonCode == "network_timeout" && it.retryEligible }) { "Expected retry incident" }
}

private fun testConflictNeverSilentlyMerges() {
    val store = InMemoryOfflineSyncLocalStore()
    val service = OfflineSyncService(store) {
        SyncTransportResult.Conflict(
            reasonCode = "object_version_mismatch",
            summary = "Server version advanced during offline capture",
            serverObjectVersion = "animal-v9",
            serverStatus = "updated",
        )
    }
    val envelope = baseEnvelope(id = "env-3", actionType = SyncActionType.FeedbackSubmission)
    service.captureOffline(envelope)
    service.markReady("env-3")
    val summary = service.replayReady(nowIso = "2026-04-13T12:00:00Z")
    val saved = store.get("env-3")

    assertThat(summary.conflicts == 1) { "Expected 1 conflict" }
    assertThat(saved?.status == SyncStatus.AwaitingConflictResolution) { "Expected AwaitingConflictResolution" }
    assertThat(saved?.conflict?.resolutionMode?.name == "RejectSilentMerge") { "Expected RejectSilentMerge mode" }
    assertThat(store.listIncidents().any { it.category == "sync_conflict" }) { "Expected conflict incident diagnostic" }
}

private fun testDuplicateIdempotencyKeyIsRejectedLocally() {
    val store = InMemoryOfflineSyncLocalStore()
    val service = OfflineSyncService(store, SyncTransport { error("Should not replay") })
    val first = baseEnvelope(id = "env-4", actionType = SyncActionType.ShiftHandover, idempotencyKey = "idem-x")
    val second = baseEnvelope(id = "env-5", actionType = SyncActionType.ShiftHandover, idempotencyKey = "idem-x")
    service.captureOffline(first)
    var rejected = false
    try {
        service.captureOffline(second)
    } catch (_: IllegalArgumentException) {
        rejected = true
    }
    assertThat(rejected) { "Expected duplicate idempotency key rejection" }
}

private fun baseEnvelope(id: String, actionType: SyncActionType, idempotencyKey: String = "idem-$id"): SyncEnvelope {
    return SyncEnvelope(
        id = id,
        actionType = actionType,
        scope = SyncScope(tenantId = "tenant-1", farmId = "farm-1", siteId = "site-a"),
        payloadJson = "{\"id\":\"${'$'}id\"}",
        audit = SyncAuditSemantics(
            actorUserId = "user-1",
            actorRole = "Veterinarian",
            mobileSessionId = "session-1",
            deviceId = "device-1",
            queuedAtIso = "2026-04-13T09:59:00Z",
            clientObservedAtIso = "2026-04-13T09:59:00Z",
        ),
        idempotency = SyncIdempotency(idempotencyKey = idempotencyKey, semanticKey = "semantic-$id"),
        lineage = SyncLineage(
            clientActionId = id,
            queueSchemaVersion = "android-offline-sync-v2",
            relatedObjectType = "animal",
            relatedObjectId = "A-100",
            relatedTaskId = "task-1",
            relatedAlertId = "alert-1",
            relatedAssistantActionId = "assistant-1",
            objectLinkage = ObjectVersionLinkage(objectType = "animal", objectId = "A-100", objectVersion = "animal-v2"),
            ownershipLinkage = TaskWorklistOwnershipLinkage(taskId = "task-1", worklistId = "wl-1", ownerUserId = "user-1", ownerRole = "Veterinarian"),
            handoverLinkage = HandoverLinkage(handoverId = "handover-1", shiftLabel = "night"),
        ),
    )
}

fun main() {
    testSuccessfulReplayIsAuditSafe()
    testRetryableFailureProducesIncidentAndBackoff()
    testConflictNeverSilentlyMerges()
    testDuplicateIdempotencyKeyIsRejectedLocally()
    println("T32-09 OfflineSyncService smoke passed")
}
