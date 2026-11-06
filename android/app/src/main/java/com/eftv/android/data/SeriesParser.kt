package com.eftv.android.data

/** Dados de um episodio lidos a partir do nome do item da playlist. */
data class SeriesInfo(
    /** Nome da serie, para exibir. */
    val title: String,
    /** Chave normalizada: episodios da mesma serie compartilham a mesma chave. */
    val key: String,
    val season: Int,
    val episode: Int,
    /** Texto depois do marcador de episodio (pode ser vazio). */
    val episodeTitle: String,
)

/**
 * Le nomes como "Projeto Eu Construtor S05E26", "Casa 2x07" ou
 * "Serie X - Temporada 2 Episodio 5" e separa serie, temporada e episodio.
 *
 * Devolve null quando o nome nao tem marcador de episodio; esse item fica
 * solto na lista, como antes.
 */
object SeriesParser {

    private val SEASON_EPISODE = Regex(
        """(?i)\b[st](\d{1,2})\s*[-_. ]?\s*e(\d{1,4})\b"""
    )
    private val SEASON_WORD_EPISODE = Regex(
        """(?i)\b(?:temporada|temp|season)\s*\.?\s*(\d{1,2})\s*[-,._ ]*\s*""" +
            """(?:epis[oó]dio|episode|ep|cap[ií]tulo|cap|e)\s*\.?\s*(\d{1,4})\b"""
    )
    private val CROSS = Regex("""(?i)\b(\d{1,2})x(\d{1,3})\b""")
    private val EPISODE_ONLY = Regex(
        """(?i)\b(?:epis[oó]dio|episode|ep|cap[ií]tulo|cap)\s*\.?\s*(\d{1,4})\b"""
    )
    private val DASH_NUMBER = Regex("""^(.+?)\s+[-–]\s+(\d{1,4})$""")

    private val LEADING_JUNK = Regex("""^[\s\-–—_.:|]+""")
    private val TRAILING_JUNK = Regex("""[\s\-–—_.:|,(\[]+$""")
    private val TRAILING_YEAR = Regex("""\s*[(\[]\s*(?:19|20)\d{2}\s*[)\]]\s*$""")
    private val TRAILING_TAG = Regex(
        """(?i)(?:\s*\[[^\]]*\]""" +
            """|\s*\((?:fhd|hd|sd|4k|uhd|h\.?26[45]|hevc|\d{3,4}p)\)""" +
            """|(?:^|\s+)(?:fhd|hd|sd|4k|uhd|h\.?26[45]|hevc|\d{3,4}p))\s*$"""
    )
    private val NON_ALNUM = Regex("""[^a-z0-9]+""")

    fun parse(name: String): SeriesInfo? {
        val text = name.trim()
        if (text.isEmpty()) return null

        SEASON_EPISODE.find(text)?.let { return build(text, it, 1, 2) }
        SEASON_WORD_EPISODE.find(text)?.let { return build(text, it, 1, 2) }
        CROSS.find(text)?.let { return build(text, it, 1, 2) }
        EPISODE_ONLY.find(text)?.let { return build(text, it, null, 1) }

        DASH_NUMBER.matchEntire(text)?.let { match ->
            val title = cleanTitle(match.groupValues[1])
            val episode = match.groupValues[2].toIntOrNull() ?: return null
            return finish(title, 1, episode, "")
        }
        return null
    }

    private fun build(
        text: String,
        match: MatchResult,
        seasonGroup: Int?,
        episodeGroup: Int,
    ): SeriesInfo? {
        val season = if (seasonGroup == null) 1 else match.groupValues[seasonGroup].toIntOrNull()
        val episode = match.groupValues[episodeGroup].toIntOrNull()
        if (season == null || episode == null) return null

        val title = cleanTitle(text.substring(0, match.range.first))
        val episodeTitle = cleanEpisodeTitle(text.substring(match.range.last + 1))
        return finish(title, season, episode, episodeTitle)
    }

    private fun finish(title: String, season: Int, episode: Int, episodeTitle: String): SeriesInfo? {
        if (title.isBlank()) return null
        return SeriesInfo(
            title = title,
            key = keyOf(title),
            season = season,
            episode = episode,
            episodeTitle = episodeTitle,
        )
    }

    /** Chave de agrupamento: sem acento, sem pontuacao e sem caixa. */
    fun keyOf(title: String): String {
        val folded = title.normalizedForSearch().replace(NON_ALNUM, " ").trim()
        return folded.ifBlank { title.normalizedForSearch() }
    }

    private fun cleanTitle(raw: String): String {
        var t = LEADING_JUNK.replace(raw, "")
        t = TRAILING_JUNK.replace(t, "")
        t = TRAILING_YEAR.replace(t, "")
        t = TRAILING_JUNK.replace(t, "")
        return t.trim()
    }

    private fun cleanEpisodeTitle(raw: String): String {
        var t = LEADING_JUNK.replace(raw, "")
        while (true) {
            val next = TRAILING_TAG.replace(t, "")
            if (next == t) break
            t = next
        }
        t = TRAILING_JUNK.replace(t, "").trim()
        return if (t.length > MAX_EPISODE_TITLE) t.take(MAX_EPISODE_TITLE).trimEnd() else t
    }

    private const val MAX_EPISODE_TITLE = 90
}
