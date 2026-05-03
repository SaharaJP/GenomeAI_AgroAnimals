package com.genomeai.agroanimals.mobile.auth

data class MobileAuthDiagnostics(
    val hasStoredSession: Boolean,
    val currentSessionId: String?,
    val currentUsername: String?,
    val currentRole: String?,
    val currentTenantId: String?,
    val currentFarmIds: List<String>,
    val currentSiteIds: List<String>,
    val lastRefreshResult: String?,
    val lastRefreshAtIso: String?,
    val lastAuthFailureReason: String?,
    val lastProtectedRequestFailure: String?,
    val reLoginRequired: Boolean,
)
