package com.eftv.android.data

import java.io.BufferedReader

/**
 * Parser de playlists M3U/M3U8 (formato Xtream Codes / IPTV).
 * Processa linha a linha para nao carregar o arquivo inteiro em memoria.
 */
object M3uParser {

    private val ATTR_REGEX = Regex("""([A-Za-z0-9_-]+)\s*=\s*"([^"]*)"""")
    private const val DEFAULT_GROUP = "Sem categoria"
    private const val DEFAULT_NAME = "Sem nome"

    fun parse(reader: BufferedReader, onChannel: (Channel) -> Unit): Int {
        var pending: Pending? = null
        var count = 0
        val groups = HashMap<String, String>()

        while (true) {
            val raw = reader.readLine() ?: break
            val line = raw.trim()
            if (line.isEmpty()) continue

            when {
                line.startsWith("#EXTINF", ignoreCase = true) -> {
                    val attrs = ATTR_REGEX.findAll(line).associate {
                        it.groupValues[1].lowercase() to it.groupValues[2].trim()
                    }
                    val rawName = nameAfterAttributes(line)
                    val name = rawName
                        .ifBlank { attrs["tvg-name"].orEmpty() }
                        .ifBlank { DEFAULT_NAME }
                    val rawGroup = attrs["group-title"].orEmpty().ifBlank { DEFAULT_GROUP }
                    pending = Pending(
                        name = name,
                        group = groups.getOrPut(rawGroup) { rawGroup },
                        logo = attrs["tvg-logo"].orEmpty(),
                        tvgId = attrs["tvg-id"].orEmpty(),
                    )
                }

                line.startsWith("#EXTGRP", ignoreCase = true) -> {
                    val group = line.substringAfter(':', "").trim()
                    if (group.isNotEmpty()) {
                        pending?.group = groups.getOrPut(group) { group }
                    }
                }

                line.startsWith("#EXTVLCOPT", ignoreCase = true) -> {
                    val option = line.substringAfter(':', "")
                    when {
                        option.startsWith("http-user-agent=", ignoreCase = true) ->
                            pending?.userAgent = option.substringAfter('=').trim().ifBlank { null }

                        option.startsWith("http-referrer=", ignoreCase = true) ||
                            option.startsWith("http-referer=", ignoreCase = true) ->
                            pending?.referer = option.substringAfter('=', "").trim().ifBlank { null }
                    }
                }

                line.startsWith("#") -> Unit // comentario / metadado

                else -> {
                    val item = pending
                    if (item == null) continue
                    if (!isPlayableUrl(line)) {
                        pending = null
                        continue
                    }
                    onChannel(
                        Channel(
                            name = item.name,
                            group = item.group,
                            logo = item.logo,
                            url = line,
                            tvgId = item.tvgId,
                            userAgent = item.userAgent,
                            referer = item.referer,
                        )
                    )
                    count++
                    pending = null
                }
            }
        }
        return count
    }

    /** Nome do canal = texto depois da primeira virgula fora das aspas. */
    private fun nameAfterAttributes(line: String): String {
        var inQuotes = false
        for (index in line.indices) {
            when (line[index]) {
                '"' -> inQuotes = !inQuotes
                ',' -> if (!inQuotes) return line.substring(index + 1).trim()
            }
        }
        return ""
    }

    private fun isPlayableUrl(url: String): Boolean {
        val lower = url.lowercase()
        return lower.startsWith("http://") ||
            lower.startsWith("https://") ||
            lower.startsWith("rtmp://") ||
            lower.startsWith("rtsp://") ||
            lower.startsWith("udp://") ||
            lower.startsWith("rtp://") ||
            lower.startsWith("mms://") ||
            lower.startsWith("mmsh://")
    }

    private class Pending(
        val name: String,
        var group: String,
        val logo: String,
        val tvgId: String,
        var userAgent: String? = null,
        var referer: String? = null,
    )
}
