package com.genomeai.agroanimals.mobile.domain.sync

object SyncDiagnostics {
    fun failureIncident(
        envelope: SyncEnvelope,
        severity: SyncIncidentSeverity,
        category: String,
        reasonCode: String,
        summary: String,
        occurredAtIso: String,
        retryEligible: Boolean,
    ): SyncIncidentDiagnostic = SyncIncidentDiagnostic(
        incidentId = "incident-${envelope.id}-$reasonCode",
        envelopeId = envelope.id,
        severity = severity,
        category = category,
        reasonCode = reasonCode,
        summary = summary,
        occurredAtIso = occurredAtIso,
        retryEligible = retryEligible,
        objectLinkage = envelope.lineage.objectLinkage,
        ownershipLinkage = envelope.lineage.ownershipLinkage,
        handoverLinkage = envelope.lineage.handoverLinkage,
    )

    fun conflictIncident(
        envelope: SyncEnvelope,
        conflict: SyncConflictRecord,
        occurredAtIso: String,
    ): SyncIncidentDiagnostic = SyncIncidentDiagnostic(
        incidentId = "incident-${envelope.id}-conflict",
        envelopeId = envelope.id,
        severity = SyncIncidentSeverity.Warning,
        category = "sync_conflict",
        reasonCode = conflict.reasonCode,
        summary = conflict.summary,
        occurredAtIso = occurredAtIso,
        retryEligible = false,
        objectLinkage = envelope.lineage.objectLinkage,
        ownershipLinkage = envelope.lineage.ownershipLinkage,
        handoverLinkage = envelope.lineage.handoverLinkage,
    )
}
