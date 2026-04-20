package com.genomeai.agroanimals.mobile.auth

import com.genomeai.agroanimals.mobile.api.MobileApiClient
import com.genomeai.agroanimals.mobile.data.local.SessionStore
import com.genomeai.agroanimals.mobile.domain.Role
import kotlinx.serialization.encodeToString
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody

class ServerAuthRepository(
    private val apiClient: MobileApiClient,
    private val sessionStore: SessionStore,
    private val httpClient: OkHttpClient = OkHttpClient(),
) : AuthRepository {
    private var lastRefreshResult: String? = null
    private var lastRefreshAtIso: String? = null
    private var lastAuthFailureReason: String? = null
    private var lastProtectedRequestFailure: String? = null

    private val jsonMediaType = "application/json; charset=utf-8".toMediaType()

    override suspend fun login(request: LoginRequest): Result<MobileAuthSession> = runCatching {
        val payload = AuthLoginRequestDto(
            username = request.username,
            password = request.password,
            clientKind = "android",
            device = AuthDeviceDto(
                deviceId = request.deviceId,
                deviceLabel = request.deviceLabel,
                platform = "android",
                appVersion = request.appVersion,
            ),
        )
        val response = postJson(
            path = "/api/app/v1/auth/login",
            bodyJson = apiClient.json.encodeToString(payload),
        )
        val body = parse<AuthLoginResponseDto>(response)
        val session = body.toMobileAuthSession()
        sessionStore.write(session)
        lastAuthFailureReason = null
        lastProtectedRequestFailure = null
        session
    }.onFailure { error ->
        lastAuthFailureReason = error.message ?: "auth.login_failed"
    }

    override suspend fun refresh(): Result<MobileAuthSession> = runCatching {
        val current = requireNotNull(sessionStore.read()) { "auth.session_missing" }
        val payload = AuthRefreshRequestDto(
            refreshToken = current.refreshToken,
            device = AuthDeviceDto(
                deviceId = current.deviceId,
                deviceLabel = "GenomeAI Field",
                platform = "android",
                appVersion = "0.1.0",
            ),
        )
        val response = postJson(
            path = "/api/app/v1/auth/refresh",
            bodyJson = apiClient.json.encodeToString(payload),
        )
        val body = parse<AuthRefreshResponseDto>(response)
        val refreshed = body.toMobileAuthSession(current)
        sessionStore.write(refreshed)
        lastRefreshResult = "ok"
        lastRefreshAtIso = body.session.updatedAt
        lastAuthFailureReason = null
        refreshed
    }.onFailure { error ->
        lastRefreshResult = "failed"
        lastAuthFailureReason = error.message ?: "auth.refresh_failed"
    }

    override suspend fun logout(): Result<Unit> = runCatching {
        val current = sessionStore.read()
        postJson(
            path = "/api/app/v1/auth/logout",
            bodyJson = apiClient.json.encodeToString(AuthLogoutRequestDto(allDevices = false)),
            bearerToken = current?.accessToken,
        )
        sessionStore.clear()
    }

    suspend fun currentSession(): MobileAuthSession? = sessionStore.read()

    suspend fun loadDiagnostics(): MobileAuthDiagnostics {
        val session = sessionStore.read()
        return MobileAuthDiagnostics(
            hasStoredSession = session != null,
            currentSessionId = session?.sessionId,
            currentUsername = session?.username,
            currentRole = session?.role?.name,
            currentTenantId = session?.tenantId,
            currentFarmIds = session?.farmIds ?: emptyList(),
            currentSiteIds = session?.siteIds ?: emptyList(),
            lastRefreshResult = lastRefreshResult,
            lastRefreshAtIso = lastRefreshAtIso,
            lastAuthFailureReason = lastAuthFailureReason,
            lastProtectedRequestFailure = lastProtectedRequestFailure,
            reLoginRequired = session == null,
        )
    }

    suspend fun getServerRuntimeProof(): Result<MobileRuntimeProofDto> = runCatching {
        val session = requireNotNull(sessionStore.read()) { "auth.session_missing" }
        val response = getJson(
            path = "/api/app/v1/auth/mobile/runtime-proof",
            bearerToken = session.accessToken,
        )
        parse<MobileRuntimeProofDto>(response)
    }.onFailure { error ->
        lastProtectedRequestFailure = error.message ?: "auth.runtime_proof_failed"
    }

    suspend fun protectedGet(path: String): Result<String> = runCatching {
        val session = requireNotNull(sessionStore.read()) { "auth.session_missing" }
        val firstTry = getJson(path = path, bearerToken = session.accessToken, allow401 = true)
        if (firstTry.code == 401) {
            val refreshed = refresh().getOrThrow()
            val secondTry = getJson(path = path, bearerToken = refreshed.accessToken, allow401 = false)
            return@runCatching secondTry.body?.string().orEmpty()
        }
        firstTry.body?.string().orEmpty()
    }.onFailure { error ->
        lastProtectedRequestFailure = error.message ?: "auth.protected_request_failed"
    }

    private fun postJson(path: String, bodyJson: String, bearerToken: String? = null): okhttp3.Response {
        val requestBuilder = Request.Builder()
            .url(apiClient.backendBaseUrl() + path)
            .post(bodyJson.toRequestBody(jsonMediaType))
            .header("Accept", "application/json")
        if (!bearerToken.isNullOrBlank()) {
            requestBuilder.header("Authorization", "Bearer $bearerToken")
        }
        val response = httpClient.newCall(requestBuilder.build()).execute()
        if (!response.isSuccessful) {
            throw IllegalStateException("http.${response.code}")
        }
        return response
    }

    private fun getJson(path: String, bearerToken: String, allow401: Boolean = false): okhttp3.Response {
        val request = Request.Builder()
            .url(apiClient.backendBaseUrl() + path)
            .get()
            .header("Accept", "application/json")
            .header("Authorization", "Bearer $bearerToken")
            .build()
        val response = httpClient.newCall(request).execute()
        if (!allow401 && !response.isSuccessful) {
            throw IllegalStateException("http.${response.code}")
        }
        return response
    }

    private inline fun <reified T> parse(response: okhttp3.Response): T {
        val payload = response.body?.string().orEmpty()
        return apiClient.json.decodeFromString(payload)
    }

    private fun AuthLoginResponseDto.toMobileAuthSession(): MobileAuthSession = MobileAuthSession(
        accessToken = tokens.accessToken,
        refreshToken = tokens.refreshToken,
        sessionId = session.sessionId,
        userId = user.userId.toString(),
        username = user.username,
        role = Role.fromServerValue(user.role),
        tenantId = scope.tenantId,
        farmIds = scope.allowedFarmIds,
        siteIds = scope.allowedSiteIds,
        deviceId = session.device.deviceId ?: "android-device",
    )

    private fun AuthRefreshResponseDto.toMobileAuthSession(current: MobileAuthSession): MobileAuthSession = MobileAuthSession(
        accessToken = tokens.accessToken,
        refreshToken = tokens.refreshToken,
        sessionId = session.sessionId,
        userId = current.userId,
        username = current.username,
        role = current.role,
        tenantId = scope.tenantId,
        farmIds = scope.allowedFarmIds,
        siteIds = scope.allowedSiteIds,
        deviceId = session.device.deviceId ?: current.deviceId,
    )
}
