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
 * Cliente HTTP do backend central EFTV (login, renovacao de sessao, entrega da
 * playlist autorizada e vinculo de aparelhos). Sem dependencias externas.
 */
class EftvApi(
    private val baseUrl: String = BuildConfig.API_BASE_URL,
    private val deviceId: String? = null,
    private val deviceName: String? = null,
) {

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

    data class EmailVerificationResult(
        val message: String,
        val emailVerified: Boolean,
    )

    data class Profile(
        val email: String,
        val emailVerified: Boolean,
        val isAdmin: Boolean,
    )

    data class DeviceBinding(
        val deviceId: String,
        val deviceName: String?,
        val current: Boolean,
    )

    data class DeviceAccess(
        val limit: Int,
        val bound: Int,
        val devices: List<DeviceBinding>,
    )

    class ApiException(
        val statusCode: Int,
        val detail: String,
        val errorCode: String? = null,
    ) : IOException(detail)

    suspend fun login(email: String, password: String): TokenPair {
        val body = JSONObject()
            .put("email", email.trim())
            .put("password", password)
        return tokenPair(request("POST", "/auth/login", body = body))
    }

    suspend fun register(email: String, password: String, fullName: String? = null): TokenPair {
        val body = JSONObject()
            .put("email", email.trim())
            .put("password", password)
        fullName?.let { body.put("full_name", it) }
        return tokenPair(request("POST", "/auth/register", body = body))
    }

    suspend fun verifyEmail(token: String): EmailVerificationResult {
        val body = JSONObject().put("token", token)
        val json = request("POST", "/auth/verify-email", body = body)
        return EmailVerificationResult(
            message = json.optString("message", ""),
            emailVerified = json.optBoolean("email_verified", false),
        )
    }

    suspend fun resendVerification(email: String): String {
        val body = JSONObject().put("email", email.trim())
        val json = request("POST", "/auth/resend-verification", body = body)
        return json.optString("message", "")
    }

    suspend fun me(accessToken: String): Profile {
        val json = request("GET", "/auth/me", accessToken = accessToken)
        return Profile(
            email = json.optString("email"),
            emailVerified = json.optBoolean("email_verified", false),
            isAdmin = json.optBoolean("is_admin", false),
        )
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

    suspend fun deviceAccess(accessToken: String): DeviceAccess {
        val json = request("GET", "/player/device", accessToken = accessToken)
        val array = json.optJSONArray("devices")
        val devices = buildList {
            for (index in 0 until (array?.length() ?: 0)) {
                val item = array?.optJSONObject(index) ?: continue
                add(
                    DeviceBinding(
                        deviceId = item.optString("device_id"),
                        deviceName = item.optString("device_name").takeIf { it.isNotBlank() },
                        current = item.optBoolean("current", false),
                    )
                )
            }
        }
        return DeviceAccess(
            limit = json.optInt("limit", 1),
            bound = json.optInt("bound", devices.size),
            devices = devices,
        )
    }

    suspend fun revokeDevice(accessToken: String): String {
        val json = request("POST", "/player/device/revoke", accessToken = accessToken)
        return json.optString("message", "")
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
            connection.connectTimeout = 30_000
            connection.readTimeout = 60_000
            connection.setRequestProperty("Accept", "application/json")
            connection.setRequestProperty("User-Agent", "EFTV-Android/${BuildConfig.VERSION_NAME}")
            accessToken?.let { connection.setRequestProperty("Authorization", "Bearer $it") }
            deviceId?.let { connection.setRequestProperty("X-Device-Id", it) }
            deviceName?.let { connection.setRequestProperty("X-Device-Name", it) }

            if (body != null) {
                connection.doOutput = true
                connection.setRequestProperty("Content-Type", "application/json; charset=utf-8")
                connection.outputStream.use { it.write(body.toString().toByteArray()) }
            }

            val code = connection.responseCode
            val stream = if (code in 200..299) connection.inputStream else connection.errorStream
            val text = stream?.bufferedReader()?.use { it.readText() }.orEmpty()

            if (code !in 200..299) {
                val (detail, errorCode) = parseError(text)
                Timber.w("API %s %s -> HTTP %d %s", method, path, code, detail)
                throw ApiException(code, detail.ifBlank { "HTTP $code" }, errorCode)
            }

            if (text.isBlank()) JSONObject() else JSONObject(text)
        } finally {
            connection.disconnect()
        }
    }

    /**
     * O backend responde `detail` como texto ou como objeto
     * `{code, message}` nos erros de vinculo de aparelho.
     */
    private fun parseError(text: String): Pair<String, String?> {
        val root = runCatching { JSONObject(text) }.getOrNull() ?: return "" to null
        return when (val detail = root.opt("detail")) {
            is JSONObject -> detail.optString("message") to
                detail.optString("code").takeIf { it.isNotBlank() }

            is String -> detail to null
            else -> "" to null
        }
    }
}
