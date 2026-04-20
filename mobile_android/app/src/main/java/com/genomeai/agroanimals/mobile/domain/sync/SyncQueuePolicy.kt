package com.genomeai.agroanimals.mobile.domain.sync

object SyncQueuePolicy {
    private val safeOfflineActions = setOf(
        SyncActionType.QuickEventEntry,
        SyncActionType.TaskCompletion,
        SyncActionType.ShiftHandover,
        SyncActionType.FeedbackSubmission,
        SyncActionType.AssistantLinkedAction,
    )

    fun canQueueOffline(actionType: SyncActionType): Boolean = actionType in safeOfflineActions

    fun requiresImmediateNetwork(actionType: SyncActionType): Boolean = !canQueueOffline(actionType)

    fun requiresAuditAck(actionType: SyncActionType): Boolean = canQueueOffline(actionType)

    fun conflictResolutionMode(actionType: SyncActionType): SyncConflictResolutionMode = when (actionType) {
        SyncActionType.QuickEventEntry -> SyncConflictResolutionMode.ClientReplayRequired
        SyncActionType.TaskCompletion -> SyncConflictResolutionMode.ManualReviewRequired
        SyncActionType.ShiftHandover -> SyncConflictResolutionMode.ManualReviewRequired
        SyncActionType.FeedbackSubmission -> SyncConflictResolutionMode.RejectSilentMerge
        SyncActionType.AssistantLinkedAction -> SyncConflictResolutionMode.ManualReviewRequired
    }

    fun permitsSilentMerge(actionType: SyncActionType): Boolean = false
}
