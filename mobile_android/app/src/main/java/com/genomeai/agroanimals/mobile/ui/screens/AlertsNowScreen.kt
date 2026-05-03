package com.genomeai.agroanimals.mobile.ui.screens

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.genomeai.agroanimals.mobile.ui.components.FieldCard
import com.genomeai.agroanimals.mobile.ui.components.ScopeChipRow

@Composable
fun AlertsNowScreen(farmId: String, siteId: String?) {
    Column(modifier = Modifier.fillMaxSize().padding(16.dp)) {
        ScopeChipRow(farmId, siteId)
        FieldCard(
            title = "Alerts now",
            subtitle = "Только текущие cowside alerts",
            body = "Экран для triage по severity/confidence/reason codes из backend evidence.",
        )
    }
}
