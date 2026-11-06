package com.eftv.android.data

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Test

class SeriesParserTest {

    @Test
    fun `formato SxxExx`() {
        val info = SeriesParser.parse("Projeto Eu Construtor Matheus Emerich S05E26")
        assertNotNull(info)
        assertEquals("Projeto Eu Construtor Matheus Emerich", info!!.title)
        assertEquals(5, info.season)
        assertEquals(26, info.episode)
    }

    @Test
    fun `formato 1x01 e T01E05`() {
        val a = SeriesParser.parse("Casa de Papel 2x07")!!
        assertEquals("Casa de Papel", a.title)
        assertEquals(2, a.season)
        assertEquals(7, a.episode)

        val b = SeriesParser.parse("Casa de Papel T01E05")!!
        assertEquals(1, b.season)
        assertEquals(5, b.episode)
    }

    @Test
    fun `temporada e episodio por extenso`() {
        val info = SeriesParser.parse("Serie X - Temporada 2 Episódio 5")!!
        assertEquals("Serie X", info.title)
        assertEquals(2, info.season)
        assertEquals(5, info.episode)
    }

    @Test
    fun `so episodio assume temporada 1`() {
        val info = SeriesParser.parse("Naruto Ep 12")!!
        assertEquals("Naruto", info.title)
        assertEquals(1, info.season)
        assertEquals(12, info.episode)
    }

    @Test
    fun `titulo do episodio e etiquetas`() {
        val info = SeriesParser.parse("Serie Y S01E02 - O Reencontro [H265]")!!
        assertEquals("Serie Y", info.title)
        assertEquals("O Reencontro", info.episodeTitle)
    }

    @Test
    fun `episodios da mesma serie compartilham a chave`() {
        val a = SeriesParser.parse("Café com Leite (2020) S01E01")!!
        val b = SeriesParser.parse("CAFE COM LEITE S02E10")!!
        assertEquals(a.key, b.key)
    }

    @Test
    fun `series diferentes tem chaves diferentes`() {
        val a = SeriesParser.parse("Dark S01E01")!!
        val b = SeriesParser.parse("Dark Matter S01E01")!!
        assert(a.key != b.key)
    }

    @Test
    fun `sem marcador de episodio fica solto`() {
        assertNull(SeriesParser.parse("Novela Completa"))
        assertNull(SeriesParser.parse("S01E01"))
    }

    @Test
    fun `resolucao nao vira episodio`() {
        assertNull(SeriesParser.parse("Filme Qualquer 1920x1080"))
    }
}
