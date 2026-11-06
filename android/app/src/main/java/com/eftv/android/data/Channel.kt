package com.eftv.android.data

data class Channel(
    val name: String,
    val group: String,
    val logo: String,
    val url: String,
    val tvgId: String = "",
    val userAgent: String? = null,
    val referer: String? = null,
    val kind: ChannelKind = ChannelKind.classify(group, name, url),
    val progressMs: Long = 0L,
    val durationMs: Long = 0L,
    /** Chave da serie (vazia quando o item nao e episodio). */
    val seriesKey: String = "",
    val seriesTitle: String = "",
    val season: Int = 0,
    val episode: Int = 0,
    /** Preenchidos so no card da serie (lista agrupada). */
    val seriesSeasons: Int = 0,
    val seriesEpisodes: Int = 0,
) {
    /** Card que representa uma serie inteira; ao tocar abre temporadas e episodios. */
    val isSeriesCard: Boolean
        get() = seriesKey.isNotEmpty() && seriesEpisodes > 0

    /** Nome normalizado uma unica vez, para a busca nao recalcular a cada tecla. */
    val searchKey: String = name.normalizedForSearch()

    /** Ha progresso salvo suficiente para mostrar na capa. */
    val hasProgress: Boolean
        get() = durationMs > 0 && progressMs > 5_000

    /** Fracao assistida, entre 0 e 1. */
    val progressFraction: Float
        get() = if (durationMs <= 0) 0f else (progressMs.toFloat() / durationMs).coerceIn(0f, 1f)
}
