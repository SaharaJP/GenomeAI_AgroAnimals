package com.genomeai.agroanimals.mobile.domain.sync

object SyncLifecyclePolicy {
    fun canTransition(from: SyncStatus, to: SyncStatus): Boolean = when (from) {
        SyncStatus.Pending -> to == SyncStatus.ReadyToSync || to == SyncStatus.Cancelled
        SyncStatus.ReadyToSync -> to == SyncStatus.InFlight || to == SyncStatus.Cancelled
        SyncStatus.InFlight -> to == SyncStatus.Synced || to == SyncStatus.FailedRetryable || to == SyncStatus.FailedTerminal || to == SyncStatus.AwaitingConflictResolution
        SyncStatus.FailedRetryable -> to == SyncStatus.ReadyToSync || to == SyncStatus.Cancelled
        SyncStatus.AwaitingConflictResolution -> to == SyncStatus.ReadyToSync || to == SyncStatus.FailedTerminal || to == SyncStatus.Cancelled
        SyncStatus.Synced,
        SyncStatus.FailedTerminal,
        SyncStatus.Cancelled,
        -> false
    }

    fun nextStatusAfterFailure(failureClass: SyncFailureClass, shouldRetry: Boolean): SyncStatus = when {
        failureClass == SyncFailureClass.Conflict -> SyncStatus.AwaitingConflictResolution
        shouldRetry -> SyncStatus.FailedRetryable
        else -> SyncStatus.FailedTerminal
    }
}
