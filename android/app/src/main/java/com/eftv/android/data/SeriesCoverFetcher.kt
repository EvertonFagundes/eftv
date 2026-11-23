package com.eftv.android.data

import android.util.LruCache
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONArray
import timber.log.Timber
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder

/**
 * Busca capa de serie em API publica gratuita (TVMaze), sem chave de API.
 *
 * Usado apenas para o card da serie agrupada, ja que o provedor M3U nao
 * entrega capa propria da serie. O resultado fica em cache em memoria para
 * nao repetir a busca ao rolar a lista.
 */
object SeriesCoverFetcher {

    private val cache = LruCache<String, String?>(64)

    suspend fun fetch(name: String): String? = withContext(Dispatchers.IO) {
        val key = name.trim().lowercase()
        if (key.isBlank()) return@withContext null
        if (cache.get(key) != null || cache.snapshot().containsKey(key)) {
            return@withContext cache.get(key)
        }
        val url = try {
            val q = URLEncoder.encode(name, "UTF-8")
            val conn = URL("https://api.tvmaze.com/search/shows?q=$q").openConnection() as HttpURLConnection
            conn.connectTimeout = 8_000
            conn.readTimeout = 8_000
            conn.requestMethod = "GET"
            conn.setRequestProperty("Accept", "application/json")
            val code = conn.responseCode
            if (code !in 200..299) {
                conn.disconnect()
                null
            } else {
                val body = conn.inputStream.bufferedReader().use { it.readText() }
                conn.disconnect()
                parsePoster(body)
            }
        } catch (e: Exception) {
            Timber.w(e, "Falha ao buscar capa da serie: %s", name)
            null
        }
        cache.put(key, url)
        url
    }

    private fun parsePoster(body: String): String? {
        return try {
            val arr = JSONArray(body)
            if (arr.length() == 0) return null
            val show = arr.getJSONObject(0).optJSONObject("show") ?: return null
            val image = show.optJSONObject("image") ?: return null
            image.optString("original").takeIf { it.isNotBlank() }
                ?: image.optString("medium").takeIf { it.isNotBlank() }
        } catch (e: Exception) {
            Timber.w(e, "Falha ao parsear resposta do TVMaze")
            null
        }
    }
}