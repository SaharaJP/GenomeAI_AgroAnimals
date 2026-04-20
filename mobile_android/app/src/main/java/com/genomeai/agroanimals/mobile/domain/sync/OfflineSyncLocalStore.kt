package com.genomeai.agroanimals.mobile.domain.sync

interface OfflineSyncLocalStore {
    fun enqueue(envelope: SyncEnvelope)
    fun upsert(envelope: SyncEnvelope)
    fun get(envelopeId: String): SyncEnvelope?
    fun listReady(nowIso: String, limit: Int): List<SyncEnvelope>
    fun listPending(): List<SyncEnvelope>
    fun recordIncident(diagnostic: SyncIncidentDiagnostic)
    fun listIncidents(): List<SyncIncidentDiagnostic>
    fun containsIdempotencyKey(idempotencyKey: String): Boolean
}
