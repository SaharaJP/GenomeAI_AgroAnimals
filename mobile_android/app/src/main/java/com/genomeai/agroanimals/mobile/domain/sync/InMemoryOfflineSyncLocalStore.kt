package com.genomeai.agroanimals.mobile.domain.sync

class InMemoryOfflineSyncLocalStore : OfflineSyncLocalStore {
    private val queue = linkedMapOf<String, SyncEnvelope>()
    private val incidents = mutableListOf<SyncIncidentDiagnostic>()
    private val seenIdempotencyKeys = linkedSetOf<String>()

    override fun enqueue(envelope: SyncEnvelope) {
        queue[envelope.id] = envelope
        seenIdempotencyKeys += envelope.idempotency.idempotencyKey
    }

    override fun upsert(envelope: SyncEnvelope) {
        queue[envelope.id] = envelope
        seenIdempotencyKeys += envelope.idempotency.idempotencyKey
    }

    override fun get(envelopeId: String): SyncEnvelope? = queue[envelopeId]

    override fun listReady(nowIso: String, limit: Int): List<SyncEnvelope> = queue.values
        .filter { envelope ->
            envelope.status == SyncStatus.ReadyToSync &&
                (envelope.nextRetryAtIso == null || envelope.nextRetryAtIso <= nowIso)
        }
        .take(limit)

    override fun listPending(): List<SyncEnvelope> = queue.values.toList()

    override fun recordIncident(diagnostic: SyncIncidentDiagnostic) {
        incidents += diagnostic
    }

    override fun listIncidents(): List<SyncIncidentDiagnostic> = incidents.toList()

    override fun containsIdempotencyKey(idempotencyKey: String): Boolean = idempotencyKey in seenIdempotencyKeys
}
