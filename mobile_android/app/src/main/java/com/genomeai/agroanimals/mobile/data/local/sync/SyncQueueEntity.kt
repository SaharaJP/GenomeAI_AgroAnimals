package com.genomeai.agroanimals.mobile.data.local.sync

import androidx.room.Entity
import androidx.room.PrimaryKey

@Entity(tableName = "sync_queue")
data class SyncQueueEntity(
    @PrimaryKey val id: String,
    val actionType: String,
    val scopeJson: String,
    val payloadJson: String,
    val auditJson: String,
    val idempotencyJson: String,
    val lineageJson: String,
    val preconditionJson: String?,
    val status: String,
    val attemptCount: Int,
    val nextRetryAtIso: String?,
    val lastFailureClass: String?,
    val lastFailureCode: String?,
    val conflictJson: String?,
    val serverAckJson: String?,
)
