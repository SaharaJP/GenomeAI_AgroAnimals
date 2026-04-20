package com.genomeai.agroanimals.mobile.ui.screens

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.genomeai.agroanimals.mobile.auth.MobileAuthDiagnostics
import com.genomeai.agroanimals.mobile.auth.MobileSyncQueueDiagnostics
import com.genomeai.agroanimals.mobile.ui.components.FieldCard

@Composable
fun AuthDiagnosticsScreen(
    authDiagnostics: MobileAuthDiagnostics,
    syncDiagnostics: MobileSyncQueueDiagnostics,
) {
    Column(modifier = Modifier.fillMaxSize().padding(16.dp)) {
        FieldCard(
            title = "Session diagnostics",
            subtitle = "Текущий runtime auth/session state",
            body = "session=${authDiagnostics.currentSessionId ?: "none"}; user=${authDiagnostics.currentUsername ?: "anonymous"}; role=${authDiagnostics.currentRole ?: "none"}; lastRefresh=${authDiagnostics.lastRefreshResult ?: "none"}; authFailure=${authDiagnostics.lastAuthFailureReason ?: "none"}; protectedFailure=${authDiagnostics.lastProtectedRequestFailure ?: "none"}; reloginRequired=${authDiagnostics.reLoginRequired}",
        )
        Text("Offline queue: pending=${syncDiagnostics.pendingCount}, ready=${syncDiagnostics.readyCount}, conflicts=${syncDiagnostics.awaitingConflictCount}, retryable=${syncDiagnostics.retryableCount}, terminal=${syncDiagnostics.terminalCount}")
        Text("Latest sync/auth reason: ${syncDiagnostics.latestIncidentReason ?: authDiagnostics.lastAuthFailureReason ?: "none"}")
    }
}
