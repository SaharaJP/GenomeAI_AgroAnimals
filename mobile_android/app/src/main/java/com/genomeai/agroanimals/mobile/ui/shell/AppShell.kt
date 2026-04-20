package com.genomeai.agroanimals.mobile.ui.shell

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.genomeai.agroanimals.mobile.auth.AuthSessionManager
import com.genomeai.agroanimals.mobile.auth.MobileAuthDiagnostics
import com.genomeai.agroanimals.mobile.auth.MobileSyncQueueDiagnostics
import com.genomeai.agroanimals.mobile.domain.Role
import com.genomeai.agroanimals.mobile.navigation.AppDestinations
import com.genomeai.agroanimals.mobile.navigation.RoleAwareNavigation
import com.genomeai.agroanimals.mobile.ui.screens.AlertsNowScreen
import com.genomeai.agroanimals.mobile.ui.screens.AuthDiagnosticsScreen
import com.genomeai.agroanimals.mobile.ui.screens.LoginScreen
import com.genomeai.agroanimals.mobile.ui.screens.QuickAnimalCardScreen
import com.genomeai.agroanimals.mobile.ui.screens.QuickEventEntryScreen
import com.genomeai.agroanimals.mobile.ui.screens.ShiftHandoverScreen
import com.genomeai.agroanimals.mobile.ui.screens.TaskCompletionScreen
import com.genomeai.agroanimals.mobile.ui.screens.TodayWorklistsScreen
import kotlinx.coroutines.launch

@Composable
fun FieldAppRoot(authSessionManager: AuthSessionManager) {
    val scope = rememberCoroutineScope()
    var loggedIn by remember { mutableStateOf(false) }
    var route by remember { mutableStateOf(AppDestinations.Login) }
    var role by remember { mutableStateOf(Role.Viewer) }
    var farmId by remember { mutableStateOf("farm-demo-1") }
    var siteId by remember { mutableStateOf<String?>("site-a") }
    var authError by remember { mutableStateOf<String?>(null) }
    var authDiagnostics by remember { mutableStateOf(emptyAuthDiagnostics()) }
    var syncDiagnostics by remember { mutableStateOf(emptySyncDiagnostics()) }

    LaunchedEffect(Unit) {
        val restored = authSessionManager.restoreSession()
        authDiagnostics = authSessionManager.diagnostics()
        syncDiagnostics = authSessionManager.syncDiagnostics()
        if (restored != null) {
            loggedIn = true
            role = restored.role
            farmId = restored.farmIds.firstOrNull() ?: farmId
            siteId = restored.siteIds.firstOrNull() ?: siteId
            route = AppDestinations.TodayWorklists
        }
    }

    if (!loggedIn) {
        LoginScreen(errorMessage = authError) { username, password ->
            scope.launch {
                val result = authSessionManager.login(
                    username = username,
                    password = password,
                    deviceId = "android-runtime-device",
                )
                result.onSuccess { session ->
                    loggedIn = true
                    role = session.role
                    farmId = session.farmIds.firstOrNull() ?: farmId
                    siteId = session.siteIds.firstOrNull() ?: siteId
                    route = AppDestinations.TodayWorklists
                    authError = null
                    authDiagnostics = authSessionManager.diagnostics()
                    syncDiagnostics = authSessionManager.syncDiagnostics()
                }.onFailure { error ->
                    authError = error.message ?: "auth.login_failed"
                    authDiagnostics = authSessionManager.diagnostics()
                }
            }
        }
        return
    }

    Column(modifier = Modifier.fillMaxSize().padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Text("GenomeAI Field / cowside app")
        Text("Android — отдельное приложение с реальным server-side auth/session path")
        Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            RoleAwareNavigation.routes(role).forEach { allowedRoute ->
                Button(onClick = { route = allowedRoute }) { Text(allowedRoute) }
            }
            Button(onClick = { route = "AuthDiagnostics" }) { Text("AuthDiagnostics") }
            Button(onClick = {
                scope.launch {
                    authSessionManager.refresh()
                    authDiagnostics = authSessionManager.diagnostics()
                }
            }) { Text("Refresh") }
            Button(onClick = {
                scope.launch {
                    authSessionManager.logout()
                    authDiagnostics = authSessionManager.diagnostics()
                    loggedIn = false
                    route = AppDestinations.Login
                }
            }) { Text("Logout") }
        }
        when (route) {
            AppDestinations.TodayWorklists -> TodayWorklistsScreen(farmId, siteId)
            AppDestinations.AlertsNow -> AlertsNowScreen(farmId, siteId)
            AppDestinations.QuickAnimalCard -> QuickAnimalCardScreen()
            AppDestinations.QuickEventEntry -> QuickEventEntryScreen { _, _ ->
                syncDiagnostics = authSessionManager.syncDiagnostics()
            }
            AppDestinations.TaskCompletion -> TaskCompletionScreen { _, _ ->
                syncDiagnostics = authSessionManager.syncDiagnostics()
            }
            AppDestinations.ShiftHandover -> ShiftHandoverScreen { _ ->
                syncDiagnostics = authSessionManager.syncDiagnostics()
            }
            "AuthDiagnostics" -> AuthDiagnosticsScreen(authDiagnostics = authDiagnostics, syncDiagnostics = syncDiagnostics)
        }
    }
}

private fun emptyAuthDiagnostics(): MobileAuthDiagnostics = MobileAuthDiagnostics(
    hasStoredSession = false,
    currentSessionId = null,
    currentUsername = null,
    currentRole = null,
    currentTenantId = null,
    currentFarmIds = emptyList(),
    currentSiteIds = emptyList(),
    lastRefreshResult = null,
    lastRefreshAtIso = null,
    lastAuthFailureReason = null,
    lastProtectedRequestFailure = null,
    reLoginRequired = true,
)

private fun emptySyncDiagnostics(): MobileSyncQueueDiagnostics = MobileSyncQueueDiagnostics(
    pendingCount = 0,
    readyCount = 0,
    awaitingConflictCount = 0,
    retryableCount = 0,
    terminalCount = 0,
    latestIncidentReason = null,
)
