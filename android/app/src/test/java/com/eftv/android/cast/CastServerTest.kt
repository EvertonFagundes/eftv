package com.eftv.android.cast

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.DataInputStream
import java.io.DataOutputStream
import java.net.Socket
import java.util.concurrent.CopyOnWriteArrayList

/**
 * Testa o servidor da TV com socket de verdade, no loopback da JVM: e o mesmo
 * caminho que o celular percorre, sem precisar de aparelho.
 */
class CastServerTest {

    private val configs = CopyOnWriteArrayList<Triple<Int, Int, ByteArray>>()
    private val videos = CopyOnWriteArrayList<Pair<Long, ByteArray>>()
    private val audioConfigs = CopyOnWriteArrayList<Triple<Int, Int, ByteArray>>()
    private val audios = CopyOnWriteArrayList<Pair<Long, ByteArray>>()
    private val connected = CopyOnWriteArrayList<Boolean>()

    private fun startServer(pin: String): CastServer {
        val server = CastServer(
            pin,
            object : CastSink {
                override fun onConfig(width: Int, height: Int, csd: ByteArray) {
                    configs += Triple(width, height, csd)
                }

                override fun onVideo(data: ByteArray, ptsUs: Long) {
                    videos += ptsUs to data
                }

                override fun onAudioConfig(sampleRate: Int, channels: Int, csd: ByteArray) {
                    audioConfigs += Triple(sampleRate, channels, csd)
                }

                override fun onAudio(data: ByteArray, ptsUs: Long) {
                    audios += ptsUs to data
                }
            },
        ) { isConnected, _ -> connected += isConnected }
        server.bind()
        server.acceptLoop()
        return server
    }

    @Test
    fun `pin errado recebe erro`() {
        val server = startServer("4821")
        try {
            Socket("127.0.0.1", server.port).use { socket ->
                val out = DataOutputStream(socket.getOutputStream())
                val input = DataInputStream(socket.getInputStream())

                CastProtocol.write(
                    out,
                    CastProtocol.TYPE_HELLO,
                    CastProtocol.helloPayload("0000", "Celular de teste"),
                )

                val reply = CastProtocol.read(input)
                assertEquals(CastProtocol.TYPE_ERROR, reply?.type)
                assertTrue(videos.isEmpty())
            }
        } finally {
            server.stop()
        }
    }

    @Test
    fun `pin certo abre a transmissao e entrega config e video`() {
        val server = startServer("4821")
        val spsPps = byteArrayOf(0, 0, 0, 1, 0x67, 0x42, 0, 0, 0, 1, 0x68, 0xCE.toByte())
        try {
            Socket("127.0.0.1", server.port).use { socket ->
                socket.tcpNoDelay = true
                val out = DataOutputStream(socket.getOutputStream())
                val input = DataInputStream(socket.getInputStream())

                CastProtocol.write(
                    out,
                    CastProtocol.TYPE_HELLO,
                    CastProtocol.helloPayload("4821", "Celular de teste"),
                )
                assertEquals(CastProtocol.TYPE_OK, CastProtocol.read(input)?.type)

                CastProtocol.write(
                    out,
                    CastProtocol.TYPE_CONFIG,
                    CastProtocol.configPayload(1280, 720, spsPps),
                )
                CastProtocol.write(
                    out,
                    CastProtocol.TYPE_VIDEO,
                    CastProtocol.videoPayload(1_000_000L, byteArrayOf(9, 8, 7, 6)),
                )

                val audioCsd = byteArrayOf(0x12, 0x10)
                CastProtocol.write(
                    out,
                    CastProtocol.TYPE_AUDIO_CONFIG,
                    CastProtocol.audioConfigPayload(44_100, 2, audioCsd),
                )
                CastProtocol.write(
                    out,
                    CastProtocol.TYPE_AUDIO,
                    CastProtocol.videoPayload(2_000_000L, byteArrayOf(5, 4, 3)),
                )
                // O servidor processa na thread de aceite; espera os callbacks.
                waitFor {
                    configs.isNotEmpty() && videos.isNotEmpty() &&
                        audioConfigs.isNotEmpty() && audios.isNotEmpty()
                }
            }
            // O fechamento do socket tambem precisa avisar a tela.
            waitFor { connected.contains(false) }
        } finally {
            server.stop()
        }

        assertEquals(1280, configs.firstOrNull()?.first)
        assertEquals(720, configs.firstOrNull()?.second)
        assertTrue(configs.firstOrNull()?.third?.contentEquals(spsPps) == true)
        assertEquals(1_000_000L, videos.firstOrNull()?.first)
        assertTrue(videos.firstOrNull()?.second?.contentEquals(byteArrayOf(9, 8, 7, 6)) == true)
        assertEquals(44_100, audioConfigs.firstOrNull()?.first)
        assertEquals(2, audioConfigs.firstOrNull()?.second)
        assertEquals(2_000_000L, audios.firstOrNull()?.first)
        assertTrue(audios.firstOrNull()?.second?.contentEquals(byteArrayOf(5, 4, 3)) == true)
        assertTrue(connected.contains(true))
        assertTrue(connected.contains(false))
    }

    @Test
    fun `depois de um pin errado outro celular consegue entrar`() {
        val server = startServer("4821")
        try {
            Socket("127.0.0.1", server.port).use { socket ->
                val out = DataOutputStream(socket.getOutputStream())
                val input = DataInputStream(socket.getInputStream())
                CastProtocol.write(
                    out,
                    CastProtocol.TYPE_HELLO,
                    CastProtocol.helloPayload("1111", "Errado"),
                )
                assertEquals(CastProtocol.TYPE_ERROR, CastProtocol.read(input)?.type)
            }

            Socket("127.0.0.1", server.port).use { socket ->
                val out = DataOutputStream(socket.getOutputStream())
                val input = DataInputStream(socket.getInputStream())
                CastProtocol.write(
                    out,
                    CastProtocol.TYPE_HELLO,
                    CastProtocol.helloPayload("4821", "Certo"),
                )
                assertEquals(CastProtocol.TYPE_OK, CastProtocol.read(input)?.type)
            }
        } finally {
            server.stop()
        }
    }

    private fun waitFor(timeoutMs: Long = 3_000, condition: () -> Boolean) {
        val deadline = System.currentTimeMillis() + timeoutMs
        while (System.currentTimeMillis() < deadline) {
            if (condition()) return
            Thread.sleep(20)
        }
    }

    private fun csd(): ByteArray = byteArrayOf(0, 0, 0, 1, 0x67, 0x42, 0, 0, 0, 1, 0x68, 0xCE.toByte())
}
