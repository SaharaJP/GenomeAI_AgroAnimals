package com.genomeai.agroanimals.mobile.ui.components

import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.AssistChip
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp

@Composable
fun ScopeChipRow(farmId: String, siteId: String?) {
    Row(modifier = Modifier.padding(vertical = 8.dp)) {
        AssistChip(onClick = {}, label = { Text("Farm: $farmId") })
        if (siteId != null) {
            AssistChip(onClick = {}, label = { Text("Site: $siteId") }, modifier = Modifier.padding(start = 8.dp))
        }
    }
}
