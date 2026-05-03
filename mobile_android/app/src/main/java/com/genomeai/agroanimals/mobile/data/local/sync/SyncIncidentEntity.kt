package com.genomeai.agroanimals.mobile.data.local.sync

import androidx.room.Entity
import androidx.room.PrimaryKey

@Entity(tableName = "sync_incidents")
data class SyncIncidentEntity(
    @PrimaryKey val incidentId: String,
    val envelopeId: String,
    val severity: String,
    val category: String,
    val reasonCode: String,
    val summary: String,
    val occurredAtIso: String,
    val retryEligible: Boolean,
    val objectLinkageJson: String?,
    val ownershipLinkageJson: String?,
    val handoverLinkageJson: String?,
)
