package com.genomeai.agroanimals.mobile.domain

data class FieldScope(
    val tenantId: String,
    val farmId: String,
    val siteId: String?,
    val role: Role
)
