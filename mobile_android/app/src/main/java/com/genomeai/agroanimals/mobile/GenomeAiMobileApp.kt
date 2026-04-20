package com.genomeai.agroanimals.mobile

import android.app.Application
import com.genomeai.agroanimals.mobile.api.MobileApiClient
import com.genomeai.agroanimals.mobile.auth.AuthSessionManager
import com.genomeai.agroanimals.mobile.auth.ServerAuthRepository
import com.genomeai.agroanimals.mobile.data.local.PreferencesSessionStore
import com.genomeai.agroanimals.mobile.domain.sync.InMemoryOfflineSyncLocalStore

class GenomeAiMobileApp : Application() {
    lateinit var authSessionManager: AuthSessionManager
        private set

    override fun onCreate() {
        super.onCreate()
        val apiClient = MobileApiClient(BuildConfig.API_BASE_URL)
        val sessionStore = PreferencesSessionStore(applicationContext)
        val syncStore = InMemoryOfflineSyncLocalStore()
        val authRepository = ServerAuthRepository(
            apiClient = apiClient,
            sessionStore = sessionStore,
        )
        authSessionManager = AuthSessionManager(
            repository = authRepository,
            syncStore = syncStore,
        )
    }
}
