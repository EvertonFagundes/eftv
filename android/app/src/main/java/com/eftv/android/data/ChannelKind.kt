package com.eftv.android.data

import java.util.Locale

/** Tipo de conteudo do catalogo. */
enum class ChannelKind {
    LIVE,
    MOVIE,
    SERIES;

    companion object {

        /** Sinais fortes de canal ao vivo (prioridade maxima). */
        private val LIVE_STRONG = listOf(
            "canal", "canais", "ao vivo", "live", "24h", "24 horas", "ppv",
        )

        /** Sinais de serie no nome do grupo. */
        private val SERIES_GROUP = listOf(
            "serie", "series", "novela", "novelas", "anime", "animes",
            "dorama", "doramas", "sitcom", "sitcoms", "temporada", "temporadas",
        )

        /** Sinais fortes de filme no nome do grupo. */
        private val MOVIE_GROUP = listOf(
            "filme", "filmes", "movie", "movies", "cinema", "cinemas", "vod",
            "lancamento", "lancamentos", "legendado", "legendados",
            "dublado", "dublados", "oscar", "premiado", "premiados",
            "classico", "classicos",
        )

        /** Generos que, sozinhos, costumam indicar catalogo sob demanda. */
        private val GENRE_HINTS = listOf(
            "acao", "comedia", "terror", "suspense", "drama", "romance",
            "ficcao", "aventura", "animacao", "guerra", "faroeste",
            "policial", "misterio", "fantasia", "familia",
        )

        /** Sinais de canal ao vivo que valem depois dos generos. */
        private val LIVE_WEAK = listOf(
            "esporte", "esportes", "noticia", "noticias", "aberto", "abertos",
            "religioso", "religiosos", "musica", "variedade", "variedades",
            "documentario", "documentarios", "infantil", "desenho", "desenhos",
        )

        private val SERIES_NAME = Regex(
            """(?i)(\bS\d{1,2}\s*E\d{1,4}\b|\b\d{1,2}x\d{1,3}\b|""" +
                """\b(?:ep|episodio|episode|cap|capitulo)\s*\.?\s*\d{1,4}\b|""" +
                """\btemporada\s*\d{1,2}\b)"""
        )

        private val VOD_EXTENSION = Regex(
            """(?i)\.(mkv|mp4|avi|mov|wmv|flv|webm|m4v|3gp|mpg|mpeg)(?:$|\?)"""
        )

        /**
         * Classifica uma entrada da playlist em ao vivo, filme ou serie.
         *
         * A maioria dos provedores IPTV marca o tipo pelo nome do grupo
         * ("Canais | Esportes", "Filmes | Acao", "Series | Drama"). Quando o
         * grupo nao ajuda, usamos o nome do item e a extensao da URL.
         */
        fun classify(group: String, name: String, url: String): ChannelKind {
            val g = group.normalizedForSearch()
            val n = name.normalizedForSearch()
            val u = url.lowercase(Locale.ROOT)

            if (LIVE_STRONG.any { g.contains(it) }) return LIVE
            if (SERIES_GROUP.any { g.contains(it) }) return SERIES
            if (MOVIE_GROUP.any { g.contains(it) }) return MOVIE

            if (SERIES_NAME.containsMatchIn(n)) return SERIES
            if (VOD_EXTENSION.containsMatchIn(u)) return MOVIE
            if (n.contains("filme") || n.contains("movie")) return MOVIE
            if (GENRE_HINTS.any { g.contains(it) }) return MOVIE
            if (LIVE_WEAK.any { g.contains(it) }) return LIVE

            // HLS (.m3u8) pode ser ao vivo ou VOD; sem pistas, assume canal.
            return LIVE
        }

        /** Grupo de conteudo adulto, em qualquer variacao de nome. */
        fun isAdultGroup(group: String?): Boolean {
            val g = group.orEmpty().normalizedForSearch()
            return g.contains("adulto") || g.contains("adult") || g.contains("xxx")
        }
    }
}

/** Posicao salva de um conteudo sob demanda. */
data class WatchProgress(
    val positionMs: Long,
    val durationMs: Long,
)
