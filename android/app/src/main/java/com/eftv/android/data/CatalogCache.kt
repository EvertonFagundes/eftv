package com.eftv.android.data

import android.content.Context
import timber.log.Timber
import java.io.File

data class CachedCatalog(
    val channels: List<Channel>,
    val updatedAt: Long,
)

/**
 * Cache local em TSV: abre o app instantaneamente sem rebaixar a playlist.
 */
object CatalogCache {

    private const val FILE_NAME = "catalog.tsv"
    private const val HEADER = "#EFTV2"
    private const val COLUMNS = 7

    fun load(context: Context, sourceId: String): CachedCatalog? {
        val file = File(context.filesDir, FILE_NAME)
        if (!file.exists()) return null

        return try {
            file.bufferedReader(Charsets.UTF_8).use { reader ->
                val header = reader.readLine() ?: return null
                val headerParts = header.split('|')
                if (headerParts.size < 4 || headerParts[0] != HEADER) return null
                // Cache de outra playlist (ou de outra versao) e descartado.
                if (headerParts[3] != sourceId) return null
                val updatedAt = headerParts[1].toLongOrNull() ?: 0L

                val channels = ArrayList<Channel>()
                while (true) {
                    val line = reader.readLine() ?: break
                    if (line.isEmpty()) continue
                    val parts = line.split('\t', limit = COLUMNS)
                    if (parts.size < COLUMNS) continue
                    val url = parts[4]
                    if (url.isEmpty()) continue
                    channels.add(
                        Channel(
                            name = parts[1],
                            group = parts[2],
                            logo = parts[3],
                            url = url,
                            tvgId = parts[0],
                            userAgent = parts[5].ifBlank { null },
                            referer = parts[6].ifBlank { null },
                        )
                    )
                }
                if (channels.isEmpty()) null else CachedCatalog(channels, updatedAt)
            }
        } catch (e: Exception) {
            Timber.w(e, "Falha ao ler o cache do catalogo")
            null
        }
    }

    fun save(context: Context, channels: List<Channel>, updatedAt: Long, sourceId: String) {
        val tmp = File(context.filesDir, "$FILE_NAME.tmp")
        val destination = File(context.filesDir, FILE_NAME)
        try {
            tmp.bufferedWriter(Charsets.UTF_8).use { writer ->
                writer.write("$HEADER|$updatedAt|${channels.size}|$sourceId\n")
                val line = StringBuilder(256)
                for (channel in channels) {
                    line.setLength(0)
                    line.append(escape(channel.tvgId)).append('\t')
                        .append(escape(channel.name)).append('\t')
                        .append(escape(channel.group)).append('\t')
                        .append(escape(channel.logo)).append('\t')
                        .append(escape(channel.url)).append('\t')
                        .append(escape(channel.userAgent.orEmpty())).append('\t')
                        .append(escape(channel.referer.orEmpty())).append('\n')
                    writer.write(line.toString())
                }
            }
            if (destination.exists()) destination.delete()
            if (!tmp.renameTo(destination)) {
                throw IllegalStateException("Nao foi possivel gravar o cache")
            }
        } catch (e: Exception) {
            Timber.w(e, "Falha ao gravar o cache do catalogo")
            tmp.delete()
        }
    }

    private fun escape(value: String): String =
        value.replace('\t', ' ').replace('\n', ' ').replace('\r', ' ')
}
