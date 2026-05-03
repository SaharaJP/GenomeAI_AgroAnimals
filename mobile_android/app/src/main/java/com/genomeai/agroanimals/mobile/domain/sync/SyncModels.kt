package com.genomeai.agroanimals.mobile.domain.sync

enum class SyncActionType {
    QuickEventEntry,
    TaskCompletion,
    ShiftHandover,
    FeedbackSubmission,
    AssistantLinkedAction,
}

enum class SyncStatus {
    Pending,
    ReadyToSync,
    InFlight,
    AwaitingConflictResolution,
    Synced,
    FailedRetryable,
    FailedTerminal,
    Cancelled,
}

enum class SyncFailureClass {
    RetryableNetwork,
    RetryableServer,
    Conflict,
    TerminalValidation,
    TerminalAuth,
    Cancelled,
}

enum class SyncConflictResolutionMode {
    ClientReplayRequired,
    ManualReviewRequired,
    RejectSilentMerge,
}

enum class SyncIncidentSeverity {
    Info,
    Warning,
    Error,
}

data class SyncScope(
    val tenantId: String,
    val farmId: String,
    val siteId: String?,
)

data class ObjectVersionLinkage(
    val objectType: String?,
    val objectId: String?,
    val objectVersion: String? = null,
)

data class TaskWorklistOwnershipLinkage(
    val taskId: String? = null,
    val worklistId: String? = null,
    val ownerUserId: String? = null,
    val ownerRole: String? = null,
)

data class HandoverLinkage(
    val handoverId: String? = null,
    val shiftLabel: String? = null,
    val previousHandoverId: String? = null,
)

data class SyncLineage(
    val clientActionId: String,
    val queueSchemaVersion: String,
    val relatedObjectType: String?,
    val relatedObjectId: String?,
    val relatedTaskId: String?,
    val relatedAlertId: String?,
    val relatedAssistantActionId: String?,
    val objectLinkage: ObjectVersionLinkage? = null,
    val ownershipLinkage: TaskWorklistOwnershipLinkage? = null,
    val handoverLinkage: HandoverLinkage? = null,
)

data class SyncAuditSemantics(
    val actorUserId: String,
    val actorRole: String,
    val mobileSessionId: String,
    val deviceId: String,
    val queuedAtIso: String,
    val clientObservedAtIso: String,
    val requiresServerAuditAck: Boolean = true,
)

data class SyncIdempotency(
    val idempotencyKey: String,
    val semanticKey: String,
    val dedupeWindowHours: Int = 72,
)

data class SyncPrecondition(
    val expectedObjectVersion: String? = null,
    val expectedObjectStatus: String? = null,
    val dependsOnClientActionId: String? = null,
)

data class SyncConflictRecord(
    val serverObjectVersion: String?,
    val serverStatus: String?,
    val resolutionMode: SyncConflictResolutionMode,
    val reasonCode: String,
    val summary: String,
)

data class SyncServerAck(
    val serverAuditId: String,
    val acceptedAtIso: String,
    val serverObjectVersion: String? = null,
    val serverTaskOwnerUserId: String? = null,
    val serverHandoverId: String? = null,
)

data class SyncEnvelope(
    val id: String,
    val actionType: SyncActionType,
    val scope: SyncScope,
    val payloadJson: String,
    val audit: SyncAuditSemantics,
    val idempotency: SyncIdempotency,
    val lineage: SyncLineage,
    val precondition: SyncPrecondition? = null,
    val requiresAuthenticatedSession: Boolean = true,
    val status: SyncStatus = SyncStatus.Pending,
    val attemptCount: Int = 0,
    val nextRetryAtIso: String? = null,
    val lastFailureClass: SyncFailureClass? = null,
    val lastFailureCode: String? = null,
    val conflict: SyncConflictRecord? = null,
    val serverAck: SyncServerAck? = null,
)

data class SyncIncidentDiagnostic(
    val incidentId: String,
    val envelopeId: String,
    val severity: SyncIncidentSeverity,
    val category: String,
    val reasonCode: String,
    val summary: String,
    val occurredAtIso: String,
    val retryEligible: Boolean,
    val objectLinkage: ObjectVersionLinkage? = null,
    val ownershipLinkage: TaskWorklistOwnershipLinkage? = null,
    val handoverLinkage: HandoverLinkage? = null,
)

data class SyncReplaySummary(
    val processed: Int,
    val synced: Int,
    val retryableFailures: Int,
    val conflicts: Int,
    val terminalFailures: Int,
)
