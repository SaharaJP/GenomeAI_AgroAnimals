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
fun TaskCompletionScreen(onComplete: (taskId: String, outcome: String) -> Unit) {
    val taskId = remember { mutableStateOf("") }
    val outcome = remember { mutableStateOf("") }
    Column(modifier = Modifier.fillMaxSize().padding(16.dp)) {
        Text("Task completion")
        OutlinedTextField(value = taskId.value, onValueChange = { taskId.value = it }, label = { Text("Task ID") })
        OutlinedTextField(value = outcome.value, onValueChange = { outcome.value = it }, label = { Text("Outcome") })
        Button(onClick = { onComplete(taskId.value, outcome.value) }) {
            Text("Закрыть задачу")
        }
    }
}
