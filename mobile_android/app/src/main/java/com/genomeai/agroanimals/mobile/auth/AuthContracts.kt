package com.genomeai.agroanimals.mobile.auth

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
data class AuthDeviceDto(
    @SerialName("device_id") val deviceId: String? = null,
    @SerialName("device_label") val deviceLabel: String? = null,
    val platform: String? = null,
    @SerialName("app_version") val appVersion: String? = null,
)

@Serializable
data class AuthScopeDto(
    @SerialName("tenant_id") val tenantId: String = "default",
    @SerialName("allowed_farm_ids") val allowedFarmIds: List<String> = emptyList(),
    @SerialName("allowed_site_ids") val allowedSiteIds: List<String> = emptyList(),
    @SerialName("active_farm_id") val activeFarmId: String? = null,
    @SerialName("active_site_id") val activeSiteId: String? = null,
)

@Serializable
data class AuthUserDto(
    @SerialName("user_id") val userId: Int,
    val username: String,
    val role: String,
    val permissions: List<String> = emptyList(),
)

@Serializable
data class AuthSessionDto(
    @SerialName("session_id") val sessionId: String,
    @SerialName("client_kind") val clientKind: String,
    @SerialName("auth_transport") val authTransport: String,
    val status: String,
    @SerialName("created_at") val createdAt: String,
    @SerialName("updated_at") val updatedAt: String,
    @SerialName("last_seen_at") val lastSeenAt: String? = null,
    @SerialName("expires_at") val expiresAt: String? = null,
    @SerialName("refresh_expires_at") val refreshExpiresAt: String? = null,
    val device: AuthDeviceDto = AuthDeviceDto(),
    val scope: AuthScopeDto,
    val current: Boolean = false,
)

@Serializable
data class AuthTokenBundleDto(
    @SerialName("token_type") val tokenType: String = "Bearer",
    @SerialName("access_token") val accessToken: String,
    @SerialName("refresh_token") val refreshToken: String,
    @SerialName("expires_in_sec") val expiresInSec: Int,
    @SerialName("refresh_expires_in_sec") val refreshExpiresInSec: Int,
)

@Serializable
data class AuthLoginRequestDto(
    val username: String,
    val password: String,
    @SerialName("tenant_id") val tenantId: String = "default",
    @SerialName("client_kind") val clientKind: String = "android",
    @SerialName("issue_web_session_cookie") val issueWebSessionCookie: Boolean = false,
    @SerialName("active_farm_id") val activeFarmId: String? = null,
    @SerialName("active_site_id") val activeSiteId: String? = null,
    val device: AuthDeviceDto,
)

@Serializable
data class AuthRefreshRequestDto(
    @SerialName("refresh_token") val refreshToken: String,
    val device: AuthDeviceDto,
)

@Serializable
data class AuthLogoutRequestDto(
    @SerialName("all_devices") val allDevices: Boolean = false,
)

@Serializable
data class AuthLoginResponseDto(
    val schema: String,
    val user: AuthUserDto,
    val session: AuthSessionDto,
    val scope: AuthScopeDto,
    val tokens: AuthTokenBundleDto,
)

@Serializable
data class AuthRefreshResponseDto(
    val schema: String,
    val session: AuthSessionDto,
    val scope: AuthScopeDto,
    val tokens: AuthTokenBundleDto,
)

@Serializable
data class AuthLogoutResponseDto(
    val schema: String,
    @SerialName("revoked_session_ids") val revokedSessionIds: List<String> = emptyList(),
)

@Serializable
data class AuthMeResponseDto(
    val schema: String,
    val user: AuthUserDto,
    val session: AuthSessionDto,
    val scope: AuthScopeDto,
)

@Serializable
data class MobileRuntimeProofDto(
    val schema: String,
    @SerialName("storage_backend") val storageBackend: String,
    @SerialName("auth_backend") val authBackend: String,
    @SerialName("request_auth_transport") val requestAuthTransport: String,
    @SerialName("refresh_lineage_count") val refreshLineageCount: Int,
    @SerialName("revoke_status") val revokeStatus: String,
    val session: AuthSessionDto,
    val scope: AuthScopeDto,
)
