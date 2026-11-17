package com.eftv.android.cast

import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test
import java.io.ByteArrayInputStream
import java.io.ByteArrayOutputStream
import java.io.DataInputStream
import java.io.DataOutputStream

class CastProtocolTest {

    @Test
    fun `mensagem sobrevive a ida e volta`() {
        val bytes = ByteArrayOutputStream()
        CastProtocol.write(DataOutputStream(bytes), CastProtocol.TYPE_OK, byteArrayOf(1, 2, 3))

        val message = CastProtocol.read(DataInputStream(ByteArrayInputStream(bytes.toByteArray())))

        assertEquals(CastProtocol.TYPE_OK, message?.type)
        assertArrayEquals(byteArrayOf(1, 2, 3), message?.payload)
    }

    @Test
    fun `hello separa pin e nome do aparelho`() {
        val payload = CastProtocol.helloPayload("4821", "Xiaomi 24117RN76G")
        val parsed = CastProtocol.parseHello(payload)

        assertEquals("4821", parsed?.first)
        assertEquals("Xiaomi 24117RN76G", parsed?.second)
    }

    @Test
    fun `hello sem pin valido e recusado`() {
        assertNull(CastProtocol.parseHello("12\nAparelho".toByteArray()))
    }

    @Test
    fun `config preserva tamanho e spspps`() {
        val csd = byteArrayOf(0, 0, 0, 1, 0x67, 0x42, 0, 0, 0, 1, 0x68, 0xCE.toByte())
        val payload = CastProtocol.configPayload(1280, 720, csd)
        val parsed = CastProtocol.parseConfig(payload)

        assertEquals(1280, parsed?.first)
        assertEquals(720, parsed?.second)
        assertArrayEquals(csd, parsed?.third)
    }

    @Test
    fun `video preserva timestamp e amostra`() {
        val sample = ByteArray(300) { it.toByte() }
        val payload = CastProtocol.videoPayload(123_456_789L, sample)
        val parsed = CastProtocol.parseVideo(payload)

        assertEquals(123_456_789L, parsed?.first)
        assertArrayEquals(sample, parsed?.second)
    }

    @Test
    fun `video vazio e recusado`() {
        assertNull(CastProtocol.parseVideo(ByteArray(8)))
    }

    @Test
    fun `pin gerado tem quatro digitos`() {
        repeat(50) {
            val pin = CastProtocol.randomPin()
            assertEquals(4, pin.length)
            assertEquals(pin.toInt(), pin.toInt())
        }
    }
}
