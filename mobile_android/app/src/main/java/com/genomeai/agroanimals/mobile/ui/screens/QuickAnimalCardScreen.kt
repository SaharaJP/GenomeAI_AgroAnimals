package com.genomeai.agroanimals.mobile.ui.screens

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.genomeai.agroanimals.mobile.ui.components.FieldCard

@Composable
fun QuickAnimalCardScreen() {
    Column(modifier = Modifier.fillMaxSize().padding(16.dp)) {
        FieldCard(
            title = "Quick animal card",
            subtitle = "Минимальный объектный контекст",
            body = "Краткий animal context: status, parity, recent alerts, active tasks, withdrawal flags.",
        )
    }
}
