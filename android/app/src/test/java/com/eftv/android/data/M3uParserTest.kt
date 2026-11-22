package com.eftv.android.data

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.BufferedReader
import java.io.StringReader

class M3uParserTest {

    private fun parse(content: String): List<Channel> {
        val channels = ArrayList<Channel>()
        val reader: BufferedReader = StringReader(content).buffered()
        M3uParser.parse(reader) { channels.add(it) }
        return channels
    }

    private fun parse(content: String, baseUrl: String): List<Channel> {
        val channels = ArrayList<Channel>()
        val reader: BufferedReader = StringReader(content).buffered()
        M3uParser.parse(reader, baseUrl) { channels.add(it) }
        return channels
    }

    @Test
    fun `le atributos, categoria e nome depois da virgula`() {
        val list = parse(
            """
            #EXTM3U
            #EXTINF:-1 tvg-id="globo.br" tvg-name="Globo" tvg-logo="https://img/globo.png" group-title="Canais | Abertos",Globo HD
            http://example.com/globo.m3u8
            """.trimIndent()
        )

        assertEquals(1, list.size)
        val channel = list[0]
        assertEquals("Globo HD", channel.name)
        assertEquals("Canais | Abertos", channel.group)
        assertEquals("https://img/globo.png", channel.logo)
        assertEquals("http://example.com/globo.m3u8", channel.url)
        assertEquals("globo.br", channel.tvgId)
    }

    @Test
    fun `virgula dentro de aspas nao corta o nome`() {
        val list = parse(
            """
            #EXTINF:-1 tvg-name="Teste, com virgula" group-title="Filmes",Nome real, com virgula
            https://example.com/a.m3u8
            """.trimIndent()
        )

        assertEquals("Nome real, com virgula", list.single().name)
    }

    @Test
    fun `usa tvg-name quando o nome estiver vazio`() {
        val list = parse(
            """
            #EXTINF:-1 tvg-name="Canal X" group-title="G",
            https://example.com/x.m3u8
            """.trimIndent()
        )

        assertEquals("Canal X", list.single().name)
    }

    @Test
    fun `grupo padrao quando ausente`() {
        val list = parse(
            """
            #EXTINF:-1,Canal solto
            https://example.com/solto.m3u8
            """.trimIndent()
        )

        assertEquals("Sem categoria", list.single().group)
    }

    @Test
    fun `extgrp sobrescreve o grupo`() {
        val list = parse(
            """
            #EXTINF:-1 group-title="Antigo",Canal
            #EXTGRP:Novo Grupo
            https://example.com/c.m3u8
            """.trimIndent()
        )

        assertEquals("Novo Grupo", list.single().group)
    }

    @Test
    fun `le opcoes do vlc por canal`() {
        val list = parse(
            """
            #EXTINF:-1,Canal protegido
            #EXTVLCOPT:http-user-agent=MeuPlayer/1.0
            #EXTVLCOPT:http-referrer=https://site.com/
            https://example.com/protegido.m3u8
            """.trimIndent()
        )

        val channel = list.single()
        assertEquals("MeuPlayer/1.0", channel.userAgent)
        assertEquals("https://site.com/", channel.referer)
    }

    @Test
    fun `ignora linhas sem url reproduzivel e canais sem extinf`() {
        val list = parse(
            """
            #EXTM3U
            #EXTINF:-1,Sem URL
            #EXTINF:-1,Arquivo local
            /sdcard/video.mkv
            https://example.com/orfao.m3u8
            #EXTINF:-1,Canal valido
            https://example.com/ok.m3u8
            """.trimIndent()
        )

        assertEquals(1, list.size)
        assertEquals("Canal valido", list.single().name)
    }

    @Test
    fun `suporta crlf`() {
        val content = "#EXTM3U\r\n#EXTINF:-1,Canal\r\nhttps://example.com/a.m3u8\r\n"
        assertEquals(1, parse(content).size)
    }

    @Test
    fun `sem opcoes extras os campos ficam nulos`() {
        val channel = parse(
            """
            #EXTINF:-1,Canal
            https://example.com/a.m3u8
            """.trimIndent()
        ).single()

        assertNull(channel.userAgent)
        assertNull(channel.referer)
    }

    @Test
    fun `resolve logo relativo contra a url da playlist`() {
        val list = parse(
            """
            #EXTINF:-1 tvg-logo="The-Walking-Dead.png",The Walking Dead
            https://example.com/a.m3u8
            """.trimIndent(),
            baseUrl = "https://example.com/listas/canais.m3u",
        )

        assertEquals(
            "https://example.com/listas/The-Walking-Dead.png",
            list.single().logo,
        )
    }

    @Test
    fun `atributo tvg-logo duplicado prefere a url absoluta`() {
        val list = parse(
            """
            #EXTINF:-1 tvg-logo="Prison-Break.png" tvg-logo="https://cdn.example.com/prison.png",Prison Break
            https://example.com/a.m3u8
            """.trimIndent(),
            baseUrl = "https://example.com/listas/canais.m3u",
        )

        assertEquals("https://cdn.example.com/prison.png", list.single().logo)
    }

    @Test
    fun `logo invalido vira vazio para usar a capa gerada`() {
        val list = parse(
            """
            #EXTINF:-1 tvg-logo="xx",Canal
            https://example.com/a.m3u8
            """.trimIndent()
        )

        assertEquals("", list.single().logo)
    }

    @Test
    fun `logo protocolo relativo vira https`() {
        val list = parse(
            """
            #EXTINF:-1 tvg-logo="//cdn.example.com/logo.png",Canal
            https://example.com/a.m3u8
            """.trimIndent()
        )

        assertEquals("https://cdn.example.com/logo.png", list.single().logo)
    }

    @Test
    fun `normalizacao remove acento e espacos duplicados`() {
        assertEquals("globoplay hd", "  GloboPlay   HD ".normalizedForSearch())
        assertEquals("sao paulo", "São   Paulo".normalizedForSearch())
        assertTrue("Ação".normalizedForSearch().startsWith("acao"))
    }
}
