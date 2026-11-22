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
    context: Context,
    private val source: PlaylistSource = PlaylistSource.local(),
) {

    private val appContext = context.applicationContext
    val catalogStore = CatalogStore.get(appContext)

    private val sourceId: String =
        if (source.url.isBlank()) {
            "assets-v2"
        } else {
            Integer.toHexString(source.url.hashCode())
        }

    /** Base para resolver logos relativos vindos na playlist. */
    private val playlistBaseUrl: String? =
        source.url.takeIf { it.startsWith("http://") || it.startsWith("https://") }

    data class Result(
        val metadata: CatalogStore.Metadata,
        val fromCache: Boolean = false,
        val error: Throwable? = null,
    )

    fun cached(): CatalogStore.Metadata? =
        catalogStore.metadata()?.takeIf { it.sourceId == sourceId }

    suspend fun refresh(onProgress: ((Int) -> Unit)? = null): Result = withContext(Dispatchers.IO) {
        var input: InputStream? = null
        try {
            input = if (source.url.isNotBlank()) openPlaylistInput() else null
            val playlistInput = input
            val metadata = catalogStore.replace(sourceId, onProgress) { onChannel ->
                if (playlistInput != null) {
                    playlistInput.bufferedReader(Charsets.UTF_8).use { reader ->
                        M3uParser.parse(reader, playlistBaseUrl, onChannel)
                    }
                } else {
                    appContext.assets.open("sample_playlist.m3u").bufferedReader(Charsets.UTF_8)
                        .use { reader ->
                            M3uParser.parse(reader, onChannel = onChannel)
                        }
                }
            }

            // Cache antigo em TSV nao e mais usado.
            appContext.deleteFile("catalog.tsv")
            appContext.deleteFile("catalog.tsv.tmp")

            Timber.i("Catalogo importado: %d canais", metadata.total)
            Result(metadata)
        } catch (e: CancellationException) {
            throw e
        } catch (e: Exception) {
            // A mensagem de algumas exceções HTTP traz a URL completa, com
            // usuário/senha do provedor. O stack trace é registrado mascarado.
            Timber.e("Falha ao baixar/processar a playlist: %s", LogUtils.redactThrowable(e))
            val cached = cached()
            if (cached != null) {
                Result(cached, fromCache = true, error = e)
            } else {
                throw e
            }
        } finally {
            runCatching { input?.close() }
        }
    }

    /**
     * Abre a playlist pelo servidor local (DNS-over-HTTPS + User-Agent/Referer)
     * e cai para o download direto se ele não responder.
     *
     * Nos dados móveis a operadora às vezes não resolve o domínio do provedor
     * ou devolve um IP de bloqueio. O download direto então falha e o catálogo
     * fica vazio, mesmo com internet funcionando. O proxy local já resolvia os
     * streams assim; agora o catálogo usa o mesmo caminho.
     */
    private suspend fun openPlaylistInput(): InputStream {
        if (source.fromServer && source.url.startsWith("http")) {
            if (LocalServer.waitUntilReady(timeoutMs = 8_000)) {
                try {
                    Timber.i("Baixando playlist pelo proxy local (DoH)")
                    return openStream(LocalServer.remotePlaylistUrl(source.url))
                } catch (e: CancellationException) {
                    throw e
                } catch (e: Exception) {
                    Timber.w(
                        "Proxy local nao baixou a playlist; tentando direto: %s",
                        LogUtils.redactThrowable(e),
                    )
                }
            } else {
                Timber.w("Servidor local nao respondeu; baixando playlist direto")
            }
        }
        return openStream(source.url)
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
