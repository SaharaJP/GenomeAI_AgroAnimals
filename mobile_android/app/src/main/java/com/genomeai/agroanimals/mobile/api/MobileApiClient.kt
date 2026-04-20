package com.genomeai.agroanimals.mobile.api

import kotlinx.serialization.json.Json

class MobileApiClient(
    private val baseUrl: String,
) {
    val json: Json = Json {
        ignoreUnknownKeys = true
        encodeDefaults = true
    }

    fun backendBaseUrl(): String = baseUrl.trimEnd('/')
}
