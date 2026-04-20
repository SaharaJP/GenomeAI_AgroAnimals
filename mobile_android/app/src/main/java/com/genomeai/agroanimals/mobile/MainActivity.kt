package com.genomeai.agroanimals.mobile

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.runtime.Composable
import com.genomeai.agroanimals.mobile.auth.AuthSessionManager
import com.genomeai.agroanimals.mobile.ui.shell.FieldAppRoot

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val authSessionManager = (application as GenomeAiMobileApp).authSessionManager
        setContent {
            FieldApp(authSessionManager = authSessionManager)
        }
    }
}

@Composable
private fun FieldApp(authSessionManager: AuthSessionManager) {
    MaterialTheme {
        Surface {
            FieldAppRoot(authSessionManager = authSessionManager)
        }
    }
}
