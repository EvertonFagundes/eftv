package com.eftv.android.data

import java.io.BufferedReader
import java.net.URI
import java.util.Locale

/**
 * Parser de playlists M3U/M3U8 (formato Xtream Codes / IPTV).
 * Processa linha a linha para nao carregar o arquivo inteiro em memoria.
 */
object M3uParser {

    private val ATTR_REGEX = Regex("""([A-Za-z0-9_-]+)\s*=\s*"([^"]*)"""")
    private const val DEFAULT_GROUP = "Sem categoria"
    private const val DEFAULT_NAME = "Sem nome"

    /** Valores usados por algumas listas como "sem logo". */
    private val INVALID_LOGOS = setOf("xx", "xxx", "tvg-logo=", "null", "none", "-")

    /**
     * Le a playlist.
     *
     * [baseUrl] e a URL de onde a lista foi baixada. Ela resolve logos
     * relativos (`The-Walking-Dead.png`), comuns em listas antigas. Quando a
     * lista vem de assets do APK, [baseUrl] fica nulo.
     */
    fun parse(
        reader: BufferedReader,
        baseUrl: String? = null,
        onChannel: (Channel) -> Unit,
    ): Int {
        var pending: Pending? = null
        var count = 0
        val groups = HashMap<String, String>()

        while (true) {
            val raw = reader.readLine() ?: break
            val line = raw.trim()
            if (line.isEmpty()) continue

            when {
                line.startsWith("#EXTINF", ignoreCase = true) -> {
                    val matches = ATTR_REGEX.findAll(line).toList()
                    val attrs = matches.associate {
                        it.groupValues[1].lowercase() to it.groupValues[2].trim()
                    }
                    val logoValues = matches
                        .filter { it.groupValues[1].equals("tvg-logo", ignoreCase = true) }
                        .map { it.groupValues[2] }
                    val rawName = nameAfterAttributes(line)
                    val name = rawName
                        .ifBlank { attrs["tvg-name"].orEmpty() }
                        .ifBlank { DEFAULT_NAME }
                    val rawGroup = attrs["group-title"].orEmpty().ifBlank { DEFAULT_GROUP }
                    pending = Pending(
                        name = name,
                        group = groups.getOrPut(rawGroup) { rawGroup },
                        logo = chooseLogo(logoValues, baseUrl),
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

    /**
     * Escolhe o logo entre os atributos duplicados.
     *
     * Varias listas repetem `tvg-logo`: um nome relativo e um link absoluto.
     * O absoluto costuma ser o que funciona, entao ele tem prioridade; se so
     * houver relativo, resolvemos contra a URL da playlist.
     */
    private fun chooseLogo(values: List<String>, baseUrl: String?): String {
        val clean = values.map { it.trim() }.filter { it.isNotEmpty() }
        val chosen = clean.lastOrNull { isAbsoluteLogo(it) }
            ?: clean.lastOrNull()
            ?: return ""
        return normalizeLogo(chosen, baseUrl)
    }

    private fun isAbsoluteLogo(value: String): Boolean =
        value.startsWith("http://", ignoreCase = true) ||
            value.startsWith("https://", ignoreCase = true) ||
            value.startsWith("//") ||
            value.startsWith("data:image/", ignoreCase = true)

    private fun normalizeLogo(raw: String, baseUrl: String?): String {
        var value = raw.trim().trim('"', '\'').replace("&amp;", "&")
        if (value.isBlank() || value.lowercase(Locale.ROOT) in INVALID_LOGOS) return ""

        if (value.startsWith("//")) value = "https:$value"
        if (isAbsoluteLogo(value)) return value

        val base = baseUrl?.takeIf {
            it.startsWith("http://", ignoreCase = true) ||
                it.startsWith("https://", ignoreCase = true)
        }
        if (base.isNullOrBlank()) return value

        // URI.resolve nao aceita espaco cru; o nome do arquivo pode ter.
        val relative = value.replace(" ", "%20")
        return runCatching { URI(base).resolve(relative).toString() }.getOrDefault(value)
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
