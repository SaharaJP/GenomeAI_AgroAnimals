package com.genomeai.agroanimals.mobile.auth

import com.genomeai.agroanimals.mobile.domain.Role
import com.genomeai.agroanimals.mobile.domain.sync.OfflineSyncLocalStore

data class MobileSyncQueueDiagnostics(
    val pendingCount: Int,
    val readyCount: Int,
    val awaitingConflictCount: Int,
    val retryableCount: Int,
    val terminalCount: Int,
    val latestIncidentReason: String?,
)

class AuthSessionManager(
    private val repository: ServerAuthRepository,
    private val syncStore: OfflineSyncLocalStore,
) {
    suspend fun restoreSession(): MobileAuthSession? = repository.currentSession()

    suspend fun login(username: String, password: String, deviceId: String): Result<MobileAuthSession> {
        return repository.login(
            LoginRequest(
                username = username,
                password = password,
                deviceId = deviceId,
                deviceLabel = "GenomeAI Field",
                appVersion = "0.1.0",
            )
        )
    }

    suspend fun refresh(): Result<MobileAuthSession> = repository.refresh()

    suspend fun logout(): Result<Unit> = repository.logout()

    suspend fun diagnostics(): MobileAuthDiagnostics = repository.loadDiagnostics()

    suspend fun serverRuntimeProof(): Result<MobileRuntimeProofDto> = repository.getServerRuntimeProof()

    suspend fun activeRole(): Role? = repository.currentSession()?.role
    suspend fun activeFarmId(): String? = repository.currentSession()?.farmIds?.firstOrNull()
    suspend fun activeSiteId(): String? = repository.currentSession()?.siteIds?.firstOrNull()

    fun syncDiagnostics(): MobileSyncQueueDiagnostics {
        val queue = syncStore.listPending()
        val incidents = syncStore.listIncidents()
        return MobileSyncQueueDiagnostics(
            pendingCount = queue.size,
            readyCount = queue.count { it.status.name == "ReadyToSync" },
            awaitingConflictCount = queue.count { it.status.name == "AwaitingConflictResolution" },
            retryableCount = queue.count { it.status.name == "FailedRetryable" },
            terminalCount = queue.count { it.status.name == "FailedTerminal" },
            latestIncidentReason = incidents.firstOrNull()?.reasonCode,
        )
    }
}
