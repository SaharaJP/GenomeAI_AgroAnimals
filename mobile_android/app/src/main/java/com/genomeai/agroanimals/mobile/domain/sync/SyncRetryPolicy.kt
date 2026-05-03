package com.genomeai.agroanimals.mobile.domain.sync

object SyncRetryPolicy {
    const val MAX_RETRY_ATTEMPTS: Int = 5
    private const val BASE_DELAY_SECONDS: Int = 5
    private const val MAX_DELAY_SECONDS: Int = 300

    fun shouldRetry(failureClass: SyncFailureClass, attemptCount: Int): Boolean {
        if (attemptCount >= MAX_RETRY_ATTEMPTS) {
            return false
        }
        return when (failureClass) {
            SyncFailureClass.RetryableNetwork,
            SyncFailureClass.RetryableServer,
            -> true

            SyncFailureClass.Conflict,
            SyncFailureClass.TerminalValidation,
            SyncFailureClass.TerminalAuth,
            SyncFailureClass.Cancelled,
            -> false
        }
    }

    fun nextRetryDelaySeconds(attemptCount: Int): Int {
        val exponent = attemptCount.coerceAtLeast(0)
        val raw = BASE_DELAY_SECONDS * (1 shl exponent.coerceAtMost(6))
        return raw.coerceAtMost(MAX_DELAY_SECONDS)
    }
}
