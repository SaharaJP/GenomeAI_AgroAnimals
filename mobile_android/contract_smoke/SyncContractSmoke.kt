package com.genomeai.agroanimals.mobile.contractsmoke

import com.genomeai.agroanimals.mobile.domain.sync.SyncActionType
import com.genomeai.agroanimals.mobile.domain.sync.SyncConflictPolicy
import com.genomeai.agroanimals.mobile.domain.sync.SyncFailureClass
import com.genomeai.agroanimals.mobile.domain.sync.SyncLifecyclePolicy
import com.genomeai.agroanimals.mobile.domain.sync.SyncQueuePolicy
import com.genomeai.agroanimals.mobile.domain.sync.SyncRetryPolicy
import com.genomeai.agroanimals.mobile.domain.sync.SyncStatus

fun main() {
    check(SyncQueuePolicy.canQueueOffline(SyncActionType.QuickEventEntry))
    check(SyncQueuePolicy.canQueueOffline(SyncActionType.TaskCompletion))
    check(SyncQueuePolicy.canQueueOffline(SyncActionType.ShiftHandover))
    check(SyncQueuePolicy.canQueueOffline(SyncActionType.FeedbackSubmission))
    check(SyncQueuePolicy.canQueueOffline(SyncActionType.AssistantLinkedAction))

    check(!SyncQueuePolicy.requiresImmediateNetwork(SyncActionType.TaskCompletion))
    check(SyncQueuePolicy.requiresAuditAck(SyncActionType.AssistantLinkedAction))
    check(!SyncConflictPolicy.allowsAutomaticMerge(SyncActionType.TaskCompletion))
    check(!SyncQueuePolicy.permitsSilentMerge(SyncActionType.FeedbackSubmission))

    check(SyncRetryPolicy.shouldRetry(SyncFailureClass.RetryableNetwork, 0))
    check(!SyncRetryPolicy.shouldRetry(SyncFailureClass.Conflict, 0))
    check(SyncRetryPolicy.nextRetryDelaySeconds(1) < SyncRetryPolicy.nextRetryDelaySeconds(3))

    check(SyncLifecyclePolicy.canTransition(SyncStatus.Pending, SyncStatus.ReadyToSync))
    check(SyncLifecyclePolicy.canTransition(SyncStatus.ReadyToSync, SyncStatus.InFlight))
    check(SyncLifecyclePolicy.canTransition(SyncStatus.InFlight, SyncStatus.AwaitingConflictResolution))
    check(!SyncLifecyclePolicy.canTransition(SyncStatus.Synced, SyncStatus.Pending))

    val conflict = SyncConflictPolicy.buildConflictRecord(
        actionType = SyncActionType.TaskCompletion,
        serverObjectVersion = "task-v2",
        serverStatus = "completed",
        reasonCode = "TASK_ALREADY_COMPLETED",
        summary = "Task was already completed on the server by another actor.",
    )
    check(conflict.reasonCode == "TASK_ALREADY_COMPLETED")
    check(conflict.serverStatus == "completed")

    println("Android offline sync contract smoke OK")
}
