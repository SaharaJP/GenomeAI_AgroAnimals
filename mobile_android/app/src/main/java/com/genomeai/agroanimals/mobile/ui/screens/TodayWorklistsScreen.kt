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
fun TodayWorklistsScreen(farmId: String, siteId: String?) {
    Column(modifier = Modifier.fillMaxSize().padding(16.dp)) {
        ScopeChipRow(farmId, siteId)
        FieldCard(
            title = "Today worklists",
            subtitle = "Полевой контур / backend-first",
            body = "Показывает только backend worklists и linked task execution, без локальной бизнес-логики.",
        )
    }
}
