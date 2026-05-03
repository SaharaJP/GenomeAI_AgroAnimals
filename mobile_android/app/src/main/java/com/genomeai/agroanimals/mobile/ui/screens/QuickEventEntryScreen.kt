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
fun QuickEventEntryScreen(onQueueOffline: (animalId: String, eventType: String) -> Unit) {
    val animalId = remember { mutableStateOf("") }
    val eventType = remember { mutableStateOf("") }
    Column(modifier = Modifier.fillMaxSize().padding(16.dp)) {
        Text("Quick event entry")
        OutlinedTextField(value = animalId.value, onValueChange = { animalId.value = it }, label = { Text("Animal ID") })
        OutlinedTextField(value = eventType.value, onValueChange = { eventType.value = it }, label = { Text("Event type") })
        Button(onClick = { onQueueOffline(animalId.value, eventType.value) }) {
            Text("Поставить в sync queue")
        }
    }
}
