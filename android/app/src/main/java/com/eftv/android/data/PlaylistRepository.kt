package com.eftv.android.data

import android.content.Context
import com.eftv.android.PlaylistConfig
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import timber.log.Timber
import java.io.IOException
import java.io.InputStream
import java.net.HttpURLConnection
import java.net.URL
import java.util.zip.GZIPInputStream

class PlaylistRepository(
    private val context: Context,
    private val source: PlaylistSource = PlaylistSource.local(),
) {

    private val sourceId: String =
        if (source.url.isBlank()) {
            "assets-v2"
        } else {
            Integer.toHexString(source.url.hashCode())
        }

    data class Result(
        val channels: List<Channel>,
        val updatedAt: Long,
        val fromCache: Boolean = false,
        val error: Throwable? = null,
        val truncated: Boolean = false,
    )

    fun cached(): CachedCatalog? = CatalogCache.load(context, sourceId)

    suspend fun refresh(): Result = withContext(Dispatchers.IO) {
        try {
            // Deduplica por URL para nao repetir o mesmo stream.
            val deduped = LinkedHashMap<String, Channel>()
            var truncated = false

            val collect: (Channel) -> Unit = { channel ->
                if (deduped.size < PlaylistConfig.MAX_CHANNELS || deduped.containsKey(channel.url)) {
                    deduped[channel.url] = channel
                } else {
                    truncated = true
                }
            }

            if (source.url.isNotBlank()) {
                openStream(source.url).use { input ->
                    input.bufferedReader(Charsets.UTF_8).use { reader ->
                        M3uParser.parse(reader, collect)
                    }
                }
            } else {
                context.assets.open("sample_playlist.m3u").bufferedReader(Charsets.UTF_8).use { reader ->
                    M3uParser.parse(reader, collect)
                }
            }

            if (deduped.isEmpty()) {
                throw IOException("A playlist nao retornou nenhum canal.")
            }

            val channels = deduped.values.toList()
            val now = System.currentTimeMillis()
            CatalogCache.save(context, channels, now, sourceId)
            Timber.i("Playlist carregada: %d canais%s", channels.size, if (truncated) " (truncada)" else "")
            Result(channels, now, truncated = truncated)
        } catch (e: CancellationException) {
            throw e
        } catch (e: Exception) {
            Timber.e(e, "Falha ao baixar/processar a playlist")
            val cache = CatalogCache.load(context, sourceId)
            if (cache != null) {
                Result(cache.channels, cache.updatedAt, fromCache = true, error = e)
            } else {
                throw e
            }
        }
    }

    private fun openStream(url: String, maxRedirects: Int = 5): InputStream {
        var current = url
        var redirects = 0

        while (true) {
            val connection = URL(current).openConnection() as HttpURLConnection
            connection.connectTimeout = 20_000
            connection.readTimeout = 120_000
            connection.instanceFollowRedirects = false
            connection.setRequestProperty("User-Agent", source.userAgent.ifBlank { PlaylistConfig.USER_AGENT })
            connection.setRequestProperty("Accept", "*/*")
            connection.setRequestProperty("Accept-Encoding", "identity")
            source.referer?.takeIf { it.isNotBlank() }?.let { referer ->
                connection.setRequestProperty("Referer", referer)
            }
            connection.requestMethod = "GET"

            val code = connection.responseCode
            if (code in 300..399 && redirects < maxRedirects) {
                val location = connection.getHeaderField("Location")
                connection.disconnect()
                if (location.isNullOrBlank()) {
                    throw IOException("Redirecionamento sem Location (HTTP $code)")
                }
                current = URL(URL(current), location).toString()
                redirects++
                continue
            }

            if (code !in 200..299) {
                connection.disconnect()
                throw IOException("Servidor retornou HTTP $code ao baixar a playlist.")
            }

            val encoding = connection.contentEncoding.orEmpty().lowercase()
            val rawStream = connection.inputStream
            return if (encoding.contains("gzip")) {
                GZIPInputStream(rawStream)
            } else {
                rawStream
            }
        }
    }
}
