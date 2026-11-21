package com.eftv.android.data

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class LogUtilsTest {

    @Test
    fun `esconde usuario e senha do caminho`() {
        val url = "http://provedor.example:8080/live/joao/senha123/456.ts"
        val seguro = LogUtils.redactUrl(url)

        assertEquals("http://provedor.example:8080/….ts", seguro)
        assertFalse(seguro.contains("joao"))
        assertFalse(seguro.contains("senha123"))
    }

    @Test
    fun `esconde parametros de consulta`() {
        val seguro = LogUtils.redactUrl(
            "https://cdn.example.com/canal/index.m3u8?username=joao&password=segredo"
        )

        assertEquals("https://cdn.example.com/….m3u8?…", seguro)
        assertFalse(seguro.contains("segredo"))
    }

    @Test
    fun `url invalida nao derruba nem vaza`() {
        assertEquals("…", LogUtils.redactUrl("nao e uma url com espaço"))
        assertEquals("", LogUtils.redactUrl(null))
    }

    @Test
    fun `aceita atualizacao https publica`() {
        assertTrue(LogUtils.isSafeUpdateUrl("https://github.com/EvertonFagundes/eftv/releases/download/v1/app.apk"))
        assertTrue(LogUtils.isSafeUpdateUrl("https://eftv.onrender.com/app/eftv.apk"))
    }

    @Test
    fun `recusa http loopback e faixas privadas`() {
        assertFalse(LogUtils.isSafeUpdateUrl("http://github.com/app.apk"))
        assertFalse(LogUtils.isSafeUpdateUrl("https://localhost/app.apk"))
        assertFalse(LogUtils.isSafeUpdateUrl("https://127.0.0.1/app.apk"))
        assertFalse(LogUtils.isSafeUpdateUrl("https://192.168.0.10/app.apk"))
        assertFalse(LogUtils.isSafeUpdateUrl("https://10.1.2.3/app.apk"))
        assertFalse(LogUtils.isSafeUpdateUrl("javascript:alert(1)"))
        assertFalse(LogUtils.isSafeUpdateUrl("https://usuario:senha@exemplo.com/app.apk"))
    }
}
