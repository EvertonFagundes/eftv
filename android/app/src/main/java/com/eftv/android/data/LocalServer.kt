package com.eftv.android.data

import com.eftv.android.PlaylistConfig
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL

/**
 * Servidor EFTV embutido no aplicativo (Chaquopy).
 *
 * O server.py roda dentro do proprio APK escutando em 0.0.0.0:8124. O app
 * usa 127.0.0.1 (funciona no Wi-Fi e nos dados moveis) e a smart TV usa o IP
 * do celular na rede Wi-Fi. Nao depende de Termux, PC ou nuvem.
 */
object LocalServer {

    const val PORT = 8124
    const val BASE_URL = "http://127.0.0.1:$PORT"

    /** Playlist M3U gerada pelo servidor, com os streams ja no proxy local. */
    fun playlistSource(): PlaylistSource = PlaylistSource(
        url = "$BASE_URL/api/playlist.m3u",
        userAgent = PlaylistConfig.USER_AGENT,
        referer = null,
        fromServer = false,
    )

    /** Espera o servidor embutido responder (ele sobe junto com o app). */
    suspend fun waitUntilReady(timeoutMs: Long = 20_000): Boolean =
        withContext(Dispatchers.IO) {
            val deadline = System.currentTimeMillis() + timeoutMs
            while (System.currentTimeMillis() < deadline) {
                if (isReady()) return@withContext true
                delay(300)
            }
            false
        }

    fun isReady(): Boolean = try {
        val conn = URL("$BASE_URL/api/status").openConnection() as HttpURLConnection
        conn.connectTimeout = 1_200
        conn.readTimeout = 1_200
        conn.requestMethod = "GET"
        val ok = conn.responseCode == 200
        conn.disconnect()
        ok
    } catch (_: Exception) {
        false
    }

    /** Quantidade de playlists salvas no servidor embutido. */
    suspend fun playlistCount(): Int = withContext(Dispatchers.IO) {
        try {
            val conn = URL("$BASE_URL/api/status").openConnection() as HttpURLConnection
            conn.connectTimeout = 2_000
            conn.readTimeout = 3_000
            conn.requestMethod = "GET"
            try {
                if (conn.responseCode != 200) return@withContext 0
                val text = conn.inputStream.bufferedReader().use { it.readText() }
                JSONObject(text).optInt("playlists", 0)
            } finally {
                conn.disconnect()
            }
        } catch (_: Exception) {
            0
        }
    }

    /**
     * Adiciona uma playlist ao servidor local. O servidor baixa e interpreta
     * o .m3u/.m3u8; a lista fica salva no armazenamento do app.
     */
    suspend fun addPlaylist(
        url: String,
        userAgent: String = PlaylistConfig.USER_AGENT,
    ): String = withContext(Dispatchers.IO) {
        val payload = JSONObject()
            .put("url", url.trim())
            .put("user_agent", userAgent)

        val conn = URL("$BASE_URL/api/playlists").openConnection() as HttpURLConnection
        try {
            conn.requestMethod = "POST"
            conn.connectTimeout = 10_000
            conn.readTimeout = 180_000
            conn.doOutput = true
            conn.setRequestProperty("Content-Type", "application/json; charset=utf-8")
            conn.setRequestProperty("Accept", "application/json")
            conn.outputStream.use {
                it.write(payload.toString().toByteArray(Charsets.UTF_8))
            }

            val code = conn.responseCode
            val stream = if (code in 200..299) conn.inputStream else conn.errorStream
            val text = stream?.bufferedReader()?.use { it.readText() }.orEmpty()
            val json = runCatching { JSONObject(text) }.getOrNull()

            if (code !in 200..299 || json?.optBoolean("ok") != true) {
                val detail = json?.optString("error").orEmpty()
                throw IOException(detail.ifBlank { "HTTP $code" })
            }
            json.optString("message").ifBlank { "Playlist adicionada." }
        } finally {
            conn.disconnect()
        }
    }
}
