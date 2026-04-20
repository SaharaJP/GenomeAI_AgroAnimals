package com.genomeai.agroanimals.mobile.data.local

import android.content.Context
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.emptyPreferences
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import com.genomeai.agroanimals.mobile.auth.MobileAuthSession
import com.genomeai.agroanimals.mobile.domain.Role
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.map

private val Context.authSessionDataStore by preferencesDataStore(name = "genomeai_mobile_auth")

class PreferencesSessionStore(
    private val context: Context,
) : SessionStore {
    override suspend fun read(): MobileAuthSession? {
        val prefs = context.authSessionDataStore.data
            .map { it }
            .first()
        val accessToken = prefs[Keys.AccessToken] ?: return null
        val refreshToken = prefs[Keys.RefreshToken] ?: return null
        val sessionId = prefs[Keys.SessionId] ?: return null
        val userId = prefs[Keys.UserId] ?: return null
        val username = prefs[Keys.Username] ?: return null
        return MobileAuthSession(
            accessToken = accessToken,
            refreshToken = refreshToken,
            sessionId = sessionId,
            userId = userId,
            username = username,
            role = Role.fromServerValue(prefs[Keys.Role]),
            tenantId = prefs[Keys.TenantId] ?: "default",
            farmIds = decodePipeDelimited(prefs[Keys.FarmIds]),
            siteIds = decodePipeDelimited(prefs[Keys.SiteIds]),
            deviceId = prefs[Keys.DeviceId] ?: "android-device",
        )
    }

    override suspend fun write(session: MobileAuthSession) {
        context.authSessionDataStore.edit { prefs ->
            prefs[Keys.AccessToken] = session.accessToken
            prefs[Keys.RefreshToken] = session.refreshToken
            prefs[Keys.SessionId] = session.sessionId
            prefs[Keys.UserId] = session.userId
            prefs[Keys.Username] = session.username
            prefs[Keys.Role] = session.role.name
            prefs[Keys.TenantId] = session.tenantId
            prefs[Keys.FarmIds] = encodePipeDelimited(session.farmIds)
            prefs[Keys.SiteIds] = encodePipeDelimited(session.siteIds)
            prefs[Keys.DeviceId] = session.deviceId
        }
    }

    override suspend fun clear() {
        context.authSessionDataStore.edit { it.clear() }
    }

    private fun encodePipeDelimited(items: List<String>): String = items.joinToString(separator = "|")
    private fun decodePipeDelimited(value: String?): List<String> = value?.split('|')?.filter { it.isNotBlank() } ?: emptyList()

    private object Keys {
        val AccessToken = stringPreferencesKey("access_token")
        val RefreshToken = stringPreferencesKey("refresh_token")
        val SessionId = stringPreferencesKey("session_id")
        val UserId = stringPreferencesKey("user_id")
        val Username = stringPreferencesKey("username")
        val Role = stringPreferencesKey("role")
        val TenantId = stringPreferencesKey("tenant_id")
        val FarmIds = stringPreferencesKey("farm_ids")
        val SiteIds = stringPreferencesKey("site_ids")
        val DeviceId = stringPreferencesKey("device_id")
    }
}
