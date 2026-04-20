package com.genomeai.agroanimals.mobile.auth

interface AuthRepository {
    suspend fun login(request: LoginRequest): Result<MobileAuthSession>
    suspend fun refresh(): Result<MobileAuthSession>
    suspend fun logout(): Result<Unit>
}
