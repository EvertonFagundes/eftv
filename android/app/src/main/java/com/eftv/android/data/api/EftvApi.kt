package com.eftv.android.data.api

import com.eftv.android.BuildConfig
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject
import timber.log.Timber
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL

/**
 * Cliente HTTP do backend central EFTV (login, renovacao de sessao e
 * entrega da playlist autorizada). Sem dependencias externas.
 */
class EftvApi(private val baseUrl: String = BuildConfig.API_BASE_URL) {

    data class TokenPair(
        val accessToken: String,
        val refreshToken: String,
        val expiresInSeconds: Long,
    )

    data class PlaylistAccess(
        val playlistUrl: String,
        val userAgent: String,
        val referer: String?,
        val refreshInSeconds: Long,
        val offlineGraceSeconds: Long,
        val subscriptionStatus: String,
        val daysRemaining: Int,
    )

    class ApiException(val statusCode: Int, val detail: String) : IOException(detail)

    suspend fun login(email: String, password: String): TokenPair {
        val body = JSONObject()
            .put("email", email.trim())
            .put("password", password)
        return tokenPair(request("POST", "/auth/login", body = body))
    }

    suspend fun refresh(refreshToken: String): TokenPair {
        val body = JSONObject().put("refresh_token", refreshToken)
        return tokenPair(request("POST", "/auth/refresh", body = body))
    }

    suspend fun playlist(accessToken: String): PlaylistAccess {
        val json = request("GET", "/player/playlist", accessToken = accessToken)
        val subscription = json.optJSONObject("subscription")
        return PlaylistAccess(
            playlistUrl = json.getString("playlist_url"),
            userAgent = json.optString("user_agent", ""),
            referer = json.optString("referer", "").takeIf { it.isNotBlank() },
            refreshInSeconds = json.optLong("refresh_in", 300L),
            offlineGraceSeconds = json.optLong("offline_grace_seconds", 0L),
            subscriptionStatus = subscription?.optString("status").orEmpty(),
            daysRemaining = subscription?.optInt("days_remaining", 0) ?: 0,
        )
    }

    private fun tokenPair(json: JSONObject) = TokenPair(
        accessToken = json.getString("access_token"),
        refreshToken = json.optString("refresh_token", ""),
        expiresInSeconds = json.optLong("expires_in", 900L),
    )

    private suspend fun request(
        method: String,
        path: String,
        accessToken: String? = null,
        body: JSONObject? = null,
    ): JSONObject = withContext(Dispatchers.IO) {
        val url = URL(baseUrl.trimEnd('/') + path)
        val connection = url.openConnection() as HttpURLConnection

        try {
            connection.requestMethod = method
            connection.connectTimeout = 15_000
            connection.readTimeout = 20_000
            connection.setRequestProperty("Accept", "application/json")
            connection.setRequestProperty("User-Agent", "EFTV-Android/${BuildConfig.VERSION_NAME}")
            accessToken?.let { connection.setRequestProperty("Authorization", "Bearer $it") }

            if (body != null) {
                connection.doOutput = true
                connection.setRequestProperty("Content-Type", "application/json; charset=utf-8")
                connection.outputStream.use { it.write(body.toString().toByteArray()) }
            }

            val code = connection.responseCode
            val stream = if (code in 200..299) connection.inputStream else connection.errorStream
            val text = stream?.bufferedReader()?.use { it.readText() }.orEmpty()

            if (code !in 200..299) {
                val detail = runCatching { JSONObject(text).optString("detail") }.getOrDefault("")
                Timber.w("API %s %s -> HTTP %d %s", method, path, code, detail)
                throw ApiException(code, detail.ifBlank { "HTTP $code" })
            }

            if (text.isBlank()) JSONObject() else JSONObject(text)
        } finally {
            connection.disconnect()
        }
    }
}
