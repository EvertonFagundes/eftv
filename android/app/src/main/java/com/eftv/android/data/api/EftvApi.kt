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

    /** Resumo da assinatura exibido em "Minha assinatura". */
    data class SubscriptionOverview(
        val subscriptionId: String?,
        val planId: String,
        val planName: String,
        val planDescription: String?,
        val priceCents: Int,
        val currency: String,
        val interval: String,
        val maxDevices: Int,
        val maxStreams: Int,
        val status: String,
        val daysRemaining: Int,
        val currentPeriodEnd: String?,
        val trialEnd: String?,
        val cancelAtPeriodEnd: Boolean,
        val autoRenew: Boolean,
        val hasAccess: Boolean,
        /** Ultima cobranca aprovada: "visa", "master", etc. */
        val paymentMethod: String?,
        /** Ultimos 4 digitos do cartao, quando o servidor informa. */
        val paymentLastFour: String?,
    )

    data class CheckoutSession(
        val preferenceId: String,
        val initPoint: String,
    )

    /** Sessao de reproducao: quantas telas o plano permite e quando renovar. */
    data class StreamSessionInfo(
        val sessionId: String,
        val limit: Int,
        val active: Int,
        val heartbeatInSeconds: Long,
    )

    /** Ultima versao publicada do app (atualizacao por APK). */
    data class AppVersionInfo(
        val versionCode: Int,
        val versionName: String,
        val apkUrl: String,
        val notes: String,
        val mandatory: Boolean,
        val configured: Boolean,
    )

    /** Codigo exibido na TV para o cliente confirmar no celular. */
    data class DeviceCode(
        val code: String,
        val expiresInSeconds: Long,
        val pollInSeconds: Long,
    )

    /** Resposta do polling da TV: `approved` traz os tokens (uma vez). */
    data class DeviceCodePoll(
        val status: String,
        val tokens: TokenPair?,
        val email: String?,
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

    /** Pede o codigo de recuperacao de senha enviado por email. */
    suspend fun forgotPassword(email: String): String {
        val body = JSONObject().put("email", email.trim())
        val json = request("POST", "/auth/forgot-password", body = body)
        return json.optString("message", "")
    }

    /** Troca a senha usando o codigo recebido por email. */
    suspend fun resetPassword(email: String, code: String, newPassword: String): String {
        val body = JSONObject()
            .put("email", email.trim())
            .put("code", code.trim())
            .put("new_password", newPassword)
        val json = request("POST", "/auth/reset-password", body = body)
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

    /**
     * Exclui a conta (LGPD / exigencia da Play Store).
     *
     * O backend anonimiza o cadastro, encerra a cobranca recorrente e revoga
     * todas as sessoes; por isso o app precisa limpar a sessao local depois.
     */
    suspend fun deleteAccount(accessToken: String): String {
        val json = request("DELETE", "/auth/me", accessToken = accessToken)
        return json.optString("message", "")
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

    /** Libera todos os aparelhos da conta (util apos trocar/reinstalar o app). */
    suspend fun revokeAllDevices(accessToken: String): String {
        val json = request("POST", "/player/device/revoke-all", accessToken = accessToken)
        return json.optString("message", "")
    }

    /**
     * Registra o inicio da reproducao e aplica o limite de telas do plano.
     *
     * Lanca `ApiException(403)` com `errorCode = "stream_limit"` quando a
     * conta ja esta com todas as telas em uso.
     */
    suspend fun playStream(
        accessToken: String,
        channelUrl: String,
        channelName: String?,
    ): StreamSessionInfo {
        val body = JSONObject().put("channel_url", channelUrl)
        channelName?.takeIf { it.isNotBlank() }?.let { body.put("channel_name", it) }
        val json = request("POST", "/player/play", accessToken = accessToken, body = body)
        return StreamSessionInfo(
            sessionId = json.optString("session_id"),
            limit = json.optInt("limit", 1),
            active = json.optInt("active", 1),
            heartbeatInSeconds = json.optLong("heartbeat_in", 45L),
        )
    }

    suspend fun heartbeatStream(accessToken: String, sessionId: String) {
        val body = JSONObject().put("session_id", sessionId)
        request("POST", "/player/heartbeat", accessToken = accessToken, body = body)
    }

    suspend fun stopStream(accessToken: String, sessionId: String) {
        val body = JSONObject().put("session_id", sessionId)
        request("POST", "/player/stop", accessToken = accessToken, body = body)
    }

    /** Ultima versao publicada (consulta sem login: o app pode estar bloqueado). */
    suspend fun appVersion(): AppVersionInfo {
        val json = request("GET", "/app/version")
        return AppVersionInfo(
            versionCode = json.optInt("version_code", 0),
            versionName = json.optString("version_name", ""),
            apkUrl = json.optString("apk_url", ""),
            notes = json.optString("notes", ""),
            mandatory = json.optBoolean("mandatory", false),
            configured = json.optBoolean("update_available_from", false),
        )
    }

    // ------------------------------------------------------------------
    // Login na TV por codigo
    // ------------------------------------------------------------------

    /** A TV pede um codigo para exibir na tela. */
    suspend fun requestDeviceCode(deviceName: String?): DeviceCode {
        val body = JSONObject()
        deviceName?.takeIf { it.isNotBlank() }?.let { body.put("device_name", it.take(120)) }
        val json = request("POST", "/auth/device-code", body = body)
        return DeviceCode(
            code = json.optString("code", ""),
            expiresInSeconds = json.optLong("expires_in", 600L),
            pollInSeconds = json.optLong("poll_in", 3L),
        )
    }

    /** A TV pergunta se ja foi autorizada (os tokens vem uma unica vez). */
    suspend fun pollDeviceCode(code: String): DeviceCodePoll {
        val body = JSONObject().put("code", code)
        val json = request("POST", "/auth/device-code/poll", body = body)
        val status = json.optString("status", "invalid")
        val tokens = if (status == "approved" && json.optString("access_token").isNotBlank()) {
            tokenPair(json)
        } else {
            null
        }
        return DeviceCodePoll(
            status = status,
            tokens = tokens,
            email = json.optString("email").takeIf { it.isNotBlank() },
        )
    }

    /** O celular (conta logada) autoriza a TV digitando o codigo. */
    suspend fun approveDeviceCode(accessToken: String, code: String): String {
        val body = JSONObject().put("code", code.trim())
        val json = request("POST", "/auth/device-code/approve", accessToken = accessToken, body = body)
        return json.optString("message", "")
    }

    /** Envia um erro/travamento do app para o suporte (sem dados pessoais). */
    suspend fun reportCrash(
        message: String,
        stacktrace: String,
        appVersion: String,
        device: String,
        android: String,
    ) {
        val body = JSONObject()
            .put("message", message.take(500))
            .put("stacktrace", stacktrace.take(8000))
            .put("app_version", appVersion)
            .put("device", device)
            .put("android", android)
        request("POST", "/app/crashes", body = body)
    }

    /**
     * String opcional: `optString` do Android devolve a string "null" quando o
     * JSON traz null, o que apareceria na tela como "cartao Null final null".
     */
    private fun JSONObject.optNullableString(key: String): String? =
        if (isNull(key)) null else optString(key).takeIf { it.isNotBlank() }

    /** Plano + assinatura do usuario em uma unica chamada. */
    suspend fun subscriptionOverview(accessToken: String): SubscriptionOverview {
        val json = request("GET", "/subscriptions/current", accessToken = accessToken)
        return SubscriptionOverview(
            subscriptionId = json.optNullableString("subscription_id"),
            planId = json.optString("plan_id"),
            planName = json.optString("plan_name"),
            planDescription = json.optNullableString("plan_description"),
            priceCents = json.optInt("price_cents", 0),
            currency = json.optString("currency", "BRL"),
            interval = json.optString("interval", "month"),
            maxDevices = json.optInt("max_devices", 1),
            maxStreams = json.optInt("max_streams", 1),
            status = json.optString("status", "none"),
            daysRemaining = json.optInt("days_remaining", 0),
            currentPeriodEnd = json.optNullableString("current_period_end"),
            trialEnd = json.optNullableString("trial_end"),
            cancelAtPeriodEnd = json.optBoolean("cancel_at_period_end", false),
            autoRenew = json.optBoolean("auto_renew", false),
            hasAccess = json.optBoolean("has_access", false),
            paymentMethod = json.optNullableString("payment_method"),
            paymentLastFour = json.optNullableString("payment_last_four"),
        )
    }

    /** Cria a assinatura recorrente no Mercado Pago e devolve a URL de pagamento. */
    suspend fun createCheckout(
        accessToken: String,
        planId: String,
        appPlatform: String? = null,
    ): CheckoutSession {
        val body = JSONObject().put("plan_id", planId)
        appPlatform?.takeIf { it.isNotBlank() }?.let { body.put("app_platform", it) }
        val json = request("POST", "/subscriptions/checkout", accessToken = accessToken, body = body)
        val initPoint = json.optString("init_point")
        if (initPoint.isBlank()) {
            throw ApiException(500, "O servidor nao devolveu a URL de pagamento")
        }
        return CheckoutSession(
            preferenceId = json.optString("preference_id"),
            initPoint = initPoint,
        )
    }

    /** Cancela a renovacao; o acesso continua ate o fim do periodo pago. */
    suspend fun cancelSubscription(accessToken: String, subscriptionId: String) {
        val encoded = java.net.URLEncoder.encode(subscriptionId, "UTF-8")
        request("POST", "/subscriptions/$encoded/cancel", accessToken = accessToken)
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
            // Render free pode levar ~1 min para acordar; 60s cortava a
            // requisicao justamente no primeiro acesso do dia.
            connection.readTimeout = 120_000
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
