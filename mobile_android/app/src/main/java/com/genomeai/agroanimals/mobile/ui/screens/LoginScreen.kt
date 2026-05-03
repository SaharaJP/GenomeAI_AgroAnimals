package com.genomeai.agroanimals.mobile.ui.screens

import androidx.compose.foundation.layout.Arrangement
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
fun LoginScreen(
    errorMessage: String?,
    onLogin: (String, String) -> Unit,
) {
    val username = remember { mutableStateOf("") }
    val password = remember { mutableStateOf("") }
    Column(
        modifier = Modifier.fillMaxSize().padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Text("GenomeAI Field")
        Text("Android использует реальный server-side auth/session path, без local role picker")
        OutlinedTextField(value = username.value, onValueChange = { username.value = it }, label = { Text("Логин") })
        OutlinedTextField(value = password.value, onValueChange = { password.value = it }, label = { Text("Пароль") })
        if (!errorMessage.isNullOrBlank()) {
            Text("Ошибка: $errorMessage")
        }
        Button(onClick = { onLogin(username.value, password.value) }) {
            Text("Войти")
        }
    }
}
