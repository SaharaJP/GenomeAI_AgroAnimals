package com.genomeai.agroanimals.mobile.data.local

import com.genomeai.agroanimals.mobile.auth.MobileAuthSession

interface SessionStore {
    suspend fun read(): MobileAuthSession?
    suspend fun write(session: MobileAuthSession)
    suspend fun clear()
}
