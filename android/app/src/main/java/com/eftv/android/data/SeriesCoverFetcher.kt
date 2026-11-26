package com.eftv.android.data

import android.util.LruCache
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import timber.log.Timber
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder
import java.text.Normalizer
import kotlin.math.min

/**
 * Busca capa de serie em APIs publicas gratuitas, sem chave.
 *
 * O IMDb tem cobertura muito melhor que o TVMaze para o catalogo IPTV
 * (titulos brasileiros, novelas, doramas e series com prefixo do provedor).
 * O TVMaze fica como reserva. O resultado, inclusive "sem capa", fica em
 * cache em memoria para nao repetir a busca ao rolar a lista.
 */
object SeriesCoverFetcher {

    private data class Candidate(val score: Int, val image: String)

    private val cache = LruCache<String, String>(128)

    suspend fun fetch(name: String): String? = withContext(Dispatchers.IO) {
        val key = name.trim().lowercase()
        if (key.isBlank()) return@withContext null
        cache.get(key)?.let { cached ->
            // String vazia e o sentinela de "sem capa" (LruCache nao aceita null).
            return@withContext cached.ifBlank { null }
        }
        val url = fetchImdb(name) ?: fetchTvmaze(name)
        cache.put(key, url.orEmpty())
        url
    }

    // ------------------------------------------------------------------
    // IMDb (endpoint de sugestoes usado pelo proprio site)
    // ------------------------------------------------------------------

    private fun fetchImdb(name: String): String? = try {
        val query = URLEncoder.encode(name, "UTF-8").replace("+", "%20")
        val conn = URL("https://v3.sg.media-imdb.com/suggestion/x/$query.json")
            .openConnection() as HttpURLConnection
        conn.connectTimeout = 7_000
        conn.readTimeout = 7_000
        conn.requestMethod = "GET"
        conn.setRequestProperty("Accept", "application/json")
        conn.setRequestProperty("User-Agent", "Mozilla/5.0 (Linux; Android)")
        val code = conn.responseCode
        val body = if (code in 200..299) {
            conn.inputStream.bufferedReader().use { it.readText() }
        } else {
            null
        }
        conn.disconnect()
        body?.let { parseImdb(it, name) }
    } catch (e: Exception) {
        Timber.w(e, "Falha ao buscar capa no IMDb: %s", name)
        null
    }

    private fun parseImdb(body: String, name: String): String? {
        val items = runCatching { JSONObject(body).optJSONArray("d") }.getOrNull() ?: return null
        val query = normalize(name)
        if (query.isBlank()) return null

        val candidates = ArrayList<Candidate>()
        for (i in 0 until items.length()) {
            val item = items.optJSONObject(i) ?: continue
            val type = (item.optString("q") + " " + item.optString("qid")).lowercase()
            val isSeries = type.contains("tv series") ||
                type.contains("tv mini") ||
                type.contains("tvseries") ||
                type.contains("tvminiseries")
            if (!isSeries) continue
            val image = item.optJSONObject("i")?.optString("imageUrl").orEmpty()
            if (image.isBlank()) continue
            val title = item.optString("l")
            candidates.add(Candidate(score(query, normalize(title)), image))
        }
        if (candidates.isEmpty()) return null

        val best = candidates.maxByOrNull { it.score } ?: return null
        // Titulos do provedor costumam vir com prefixo/sufixo ("[L]", "S01",
        // "Nova Geracao"). Um unico resultado do IMDb para a consulta quase
        // sempre e o casamento certo. Nota zero acontece com titulos
        // traduzidos ("Wandinha" -> "Wednesday", "Round 6" -> "Squid Game"):
        // nesse caso vale a ordem de relevancia do proprio IMDb.
        val accept = best.score >= 25 || candidates.size == 1 || best.score == 0
        return if (accept) best.image else null
    }

    private fun score(query: String, title: String): Int {
        if (query == title) return 100
        if (title.contains(query)) return 90
        if (query.contains(title)) return 80

        val qList = query.split(' ').filter { it.length > 1 }
        val tList = title.split(' ').filter { it.length > 1 }
        val qTokens = qList.toSet()
        val tTokens = tList.toSet()
        if (qTokens.isEmpty() || tTokens.isEmpty()) return 0

        val common = qTokens.count { it in tTokens }
        val union = (qTokens + tTokens).size
        var result = (common.toDouble() / union * 80).toInt()

        // Prefixos de provedor (007, O11CE, 011ZE...) costumam virar o
        // primeiro token do titulo oficial.
        val qFirst = qList.firstOrNull().orEmpty()
        val tFirst = tList.firstOrNull().orEmpty()
        if (qFirst.isNotBlank() && tFirst.isNotBlank()) {
            val digits = qFirst.any { it.isDigit() } && tFirst.any { it.isDigit() }
            if (qFirst == tFirst) {
                result += 25
            } else if (digits && levenshtein(qFirst, tFirst) <= 2) {
                result += 20
            }
        }
        return result
    }

    private fun levenshtein(a: String, b: String): Int {
        val previous = IntArray(b.length + 1) { it }
        val current = IntArray(b.length + 1)
        for (i in 1..a.length) {
            current[0] = i
            for (j in 1..b.length) {
                current[j] = min(
                    min(current[j - 1] + 1, previous[j] + 1),
                    previous[j - 1] + if (a[i - 1] == b[j - 1]) 0 else 1,
                )
            }
            System.arraycopy(current, 0, previous, 0, current.size)
        }
        return previous[b.length]
    }

    private fun normalize(value: String): String =
        Normalizer.normalize(value, Normalizer.Form.NFD)
            .replace(Regex("\\p{M}+"), "")
            .lowercase()
            .replace(Regex("[^a-z0-9]+"), " ")
            .trim()

    // ------------------------------------------------------------------
    // TVMaze (reserva)
    // ------------------------------------------------------------------

    private fun fetchTvmaze(name: String): String? = try {
        val query = URLEncoder.encode(name, "UTF-8")
        val conn = URL("https://api.tvmaze.com/search/shows?q=$query")
            .openConnection() as HttpURLConnection
        conn.connectTimeout = 7_000
        conn.readTimeout = 7_000
        conn.requestMethod = "GET"
        conn.setRequestProperty("Accept", "application/json")
        val code = conn.responseCode
        val body = if (code in 200..299) {
            conn.inputStream.bufferedReader().use { it.readText() }
        } else {
            null
        }
        conn.disconnect()
        body?.let { parsePoster(it) }
    } catch (e: Exception) {
        Timber.w(e, "Falha ao buscar capa no TVMaze: %s", name)
        null
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
