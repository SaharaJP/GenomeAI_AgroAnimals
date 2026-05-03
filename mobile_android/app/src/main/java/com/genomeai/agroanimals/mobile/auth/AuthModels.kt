package com.genomeai.agroanimals.mobile.auth

import com.genomeai.agroanimals.mobile.domain.Role

data class MobileAuthSession(
    val accessToken: String,
    val refreshToken: String,
    val sessionId: String,
    val userId: String,
    val username: String,
    val role: Role,
    val tenantId: String,
    val farmIds: List<String>,
    val siteIds: List<String>,
    val deviceId: String,
)

data class LoginRequest(
    val username: String,
    val password: String,
    val deviceId: String,
    val deviceLabel: String,
    val appVersion: String,
)
