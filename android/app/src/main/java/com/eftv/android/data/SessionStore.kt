package com.eftv.android.data

import android.content.Context
import com.eftv.android.data.api.EftvApi

/**
 * Sessao do assinante salva localmente. O token de acesso e curto (15 min por
 * padrao) e o refresh token permite renovar sem pedir a senha de novo.
 */
class SessionStore(context: Context) {

    private val prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)

    fun save(tokens: EftvApi.TokenPair, email: String) {
        val expiresAt = System.currentTimeMillis() +
            (tokens.expiresInSeconds * 1000L) - EXPIRY_MARGIN_MS
        prefs.edit()
            .putString(KEY_ACCESS, tokens.accessToken)
            .putString(KEY_REFRESH, tokens.refreshToken)
            .putString(KEY_EMAIL, email)
            .putLong(KEY_EXPIRES_AT, expiresAt)
            .apply()
    }

    fun accessToken(): String? = prefs.getString(KEY_ACCESS, null)

    fun refreshToken(): String? = prefs.getString(KEY_REFRESH, null)

    fun email(): String? = prefs.getString(KEY_EMAIL, null)

    fun hasSession(): Boolean = !accessToken().isNullOrBlank()

    fun isAccessTokenExpired(now: Long = System.currentTimeMillis()): Boolean =
        prefs.getLong(KEY_EXPIRES_AT, 0L) <= now

    fun clear() {
        prefs.edit().clear().apply()
    }

    private companion object {
        const val PREFS = "eftv_session"
        const val KEY_ACCESS = "access_token"
        const val KEY_REFRESH = "refresh_token"
        const val KEY_EMAIL = "email"
        const val KEY_EXPIRES_AT = "expires_at"

        /** Renova um pouco antes de expirar, para nao falhar no meio do uso. */
        const val EXPIRY_MARGIN_MS = 30_000L
    }
}
