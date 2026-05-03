package com.genomeai.agroanimals.mobile.domain.sync

object SyncConflictPolicy {
    fun buildConflictRecord(
        actionType: SyncActionType,
        serverObjectVersion: String?,
        serverStatus: String?,
        reasonCode: String,
        summary: String,
    ): SyncConflictRecord {
        return SyncConflictRecord(
            serverObjectVersion = serverObjectVersion,
            serverStatus = serverStatus,
            resolutionMode = SyncQueuePolicy.conflictResolutionMode(actionType),
            reasonCode = reasonCode,
            summary = summary,
        )
    }

    fun allowsAutomaticMerge(actionType: SyncActionType): Boolean = false
}
