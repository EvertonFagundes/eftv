package com.eftv.android.data

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class ChannelKindTest {

    @Test
    fun `canais com grupo de ao vivo sao LIVE`() {
        assertEquals(
            ChannelKind.LIVE,
            ChannelKind.classify("Canais | Esportes", "ESPN", "http://x/live.m3u8"),
        )
        assertEquals(
            ChannelKind.LIVE,
            ChannelKind.classify("AO VIVO | Notícias", "CNN", "http://x/live.m3u8"),
        )
        assertEquals(
            ChannelKind.LIVE,
            ChannelKind.classify("TV Aberta", "Globo", "http://x/live.m3u8"),
        )
    }

    @Test
    fun `grupo de filmes vira MOVIE`() {
        assertEquals(
            ChannelKind.MOVIE,
            ChannelKind.classify("Filmes | Ação", "Velozes e Furiosos", "http://x/movie.m3u8"),
        )
        assertEquals(
            ChannelKind.MOVIE,
            ChannelKind.classify("Lançamentos", "Duna 2", "http://x/123.mp4"),
        )
    }

    @Test
    fun `grupo de series vira SERIES`() {
        assertEquals(
            ChannelKind.SERIES,
            ChannelKind.classify("Séries | Drama", "Breaking Bad", "http://x/serie.m3u8"),
        )
        assertEquals(
            ChannelKind.SERIES,
            ChannelKind.classify("Animes", "Naruto", "http://x/anime.m3u8"),
        )
    }

    @Test
    fun `nome com padrao de episodio vira SERIES`() {
        assertEquals(
            ChannelKind.SERIES,
            ChannelKind.classify("Sem categoria", "The Office S01E02", "http://x/1.m3u8"),
        )
        assertEquals(
            ChannelKind.SERIES,
            ChannelKind.classify("Sem categoria", "Friends 1x05", "http://x/2.m3u8"),
        )
        assertEquals(
            ChannelKind.SERIES,
            ChannelKind.classify("Sem categoria", "Lost Episodio 4", "http://x/3.m3u8"),
        )
    }

    @Test
    fun `extensao de arquivo de video vira MOVIE`() {
        assertEquals(
            ChannelKind.MOVIE,
            ChannelKind.classify("Sem categoria", "Filme Qualquer", "http://x/filme.mkv"),
        )
        assertEquals(
            ChannelKind.MOVIE,
            ChannelKind.classify("Sem categoria", "Filme Qualquer", "http://x/filme.mp4?token=1"),
        )
    }

    @Test
    fun `hls sem pistas continua LIVE`() {
        assertEquals(
            ChannelKind.LIVE,
            ChannelKind.classify("Sem categoria", "Canal 1", "http://x/1.m3u8"),
        )
    }

    @Test
    fun `grupos adultos sao detectados em variacoes`() {
        assertTrue(ChannelKind.isAdultGroup("Adultos"))
        assertTrue(ChannelKind.isAdultGroup("ADULTOS | XXX"))
        assertTrue(ChannelKind.isAdultGroup("Adulto"))
        assertFalse(ChannelKind.isAdultGroup("Filmes | Ação"))
        assertFalse(ChannelKind.isAdultGroup(null))
    }
}
