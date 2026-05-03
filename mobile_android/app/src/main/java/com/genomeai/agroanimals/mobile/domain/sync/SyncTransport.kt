package com.genomeai.agroanimals.mobile.domain.sync

sealed class SyncTransportResult {
    data class Success(
        val serverAuditId: String,
        val acceptedAtIso: String,
        val serverObjectVersion: String? = null,
        val serverTaskOwnerUserId: String? = null,
        val serverHandoverId: String? = null,
    ) : SyncTransportResult()

    data class RetryableFailure(
        val reasonCode: String,
        val summary: String,
        val failureClass: SyncFailureClass,
    ) : SyncTransportResult()

    data class Conflict(
        val reasonCode: String,
        val summary: String,
        val serverObjectVersion: String? = null,
        val serverStatus: String? = null,
    ) : SyncTransportResult()

    data class TerminalFailure(
        val reasonCode: String,
        val summary: String,
        val failureClass: SyncFailureClass,
    ) : SyncTransportResult()
}

fun interface SyncTransport {
    fun replay(envelope: SyncEnvelope): SyncTransportResult
}
