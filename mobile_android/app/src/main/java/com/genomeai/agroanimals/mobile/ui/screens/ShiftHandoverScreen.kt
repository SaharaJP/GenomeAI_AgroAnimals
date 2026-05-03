package com.genomeai.agroanimals.mobile.ui.screens

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp

@Composable
fun ShiftHandoverScreen(onSubmit: (String) -> Unit) {
    val summary = remember { mutableStateOf("") }
    Column(modifier = Modifier.fillMaxSize().padding(16.dp)) {
        Text("Shift handover")
        OutlinedTextField(value = summary.value, onValueChange = { summary.value = it }, label = { Text("Сводка смены") })
        Button(onClick = { onSubmit(summary.value) }) {
            Text("Передать смену")
        }
    }
}
