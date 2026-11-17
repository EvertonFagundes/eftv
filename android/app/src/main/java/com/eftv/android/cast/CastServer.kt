package com.eftv.android.cast

import java.io.BufferedInputStream
import java.io.BufferedOutputStream
import java.io.DataInputStream
import java.io.DataOutputStream
import java.io.IOException
import java.net.ServerSocket
import java.net.Socket
import kotlin.concurrent.thread

/**
 * Recebe a transmissao de tela do celular (lado da TV).
 *
 * Aceita uma conexao por vez, valida o PIN e repassa CONFIG/VIDEO para o
 * [CastSink] (que decodifica e desenha). Sem dependencia de Android para poder
 * ser testado na JVM: os testes sobem um servidor de verdade e falam o
 * protocolo pelo socket.
 */
interface CastSink {
    fun onConfig(width: Int, height: Int, csd: ByteArray)
    fun onVideo(data: ByteArray, ptsUs: Long)
    fun onAudioConfig(sampleRate: Int, channels: Int, csd: ByteArray)
    fun onAudio(data: ByteArray, ptsUs: Long)
}

class CastServer(
    private val pin: String,
    private val sink: CastSink,
    /** (conectado, nome do aparelho) — chamado tambem no fim da transmissao. */
    private val onState: (Boolean, String?) -> Unit,
    /** Diagnostico opcional: a TV loga tentativas, PIN errado e quedas. */
    private val onLog: (String) -> Unit = {},
) {

    private var serverSocket: ServerSocket? = null

    /** Conexao em andamento, para o stop() nao deixar a thread presa no read. */
    @Volatile
    private var clientSocket: Socket? = null

    @Volatile
    private var running = false

    private var acceptThread: Thread? = null

    /** Porta em uso (8765 ou uma livre). Valida antes de anunciar no mDNS. */
    var port: Int = 0
        private set

    /**
     * Abre o socket. E rapido e nao bloqueia, por isso pode ser chamado na
     * thread principal antes de exibir o PIN na tela.
     */
    fun bind(): Int {
        val socket = try {
            ServerSocket(CastProtocol.DEFAULT_PORT)
        } catch (_: IOException) {
            // Porta ocupada (outro app ou outra instancia): o sistema escolhe.
            ServerSocket(0)
        }
        socket.reuseAddress = true
        serverSocket = socket
        port = socket.localPort
        running = true
        return port
    }

    fun acceptLoop() {
        if (serverSocket == null) return
        acceptThread = thread(name = "eftv-cast-accept", isDaemon = true) {
            onLog("aguardando conexao")
            while (running) {
                val client = try {
                    serverSocket?.accept()
                } catch (e: IOException) {
                    if (running) onLog("accept falhou: ${e.message}")
                    break
                } ?: continue
                // Um celular por vez: a transmissao e da tela inteira.
                onLog("conexao de ${client.inetAddress?.hostAddress}")
                handle(client)
            }
            onLog("servidor encerrado")
        }
    }

    private fun handle(client: Socket) {
        var connected = false
        clientSocket = client
        try {
            client.tcpNoDelay = true
            client.soTimeout = HANDSHAKE_TIMEOUT_MS
            val input = DataInputStream(BufferedInputStream(client.getInputStream(), 256 * 1024))
            val output = DataOutputStream(BufferedOutputStream(client.getOutputStream(), 64 * 1024))

            val hello = CastProtocol.read(input)
            if (hello == null || hello.type != CastProtocol.TYPE_HELLO) {
                onLog("handshake invalido")
                replyError(output, "Handshake invalido")
                return
            }
            val parsed = CastProtocol.parseHello(hello.payload)
            if (parsed == null) {
                onLog("handshake ilegivel")
                replyError(output, "Handshake invalido")
                return
            }
            val (receivedPin, deviceName) = parsed
            if (receivedPin != pin) {
                onLog("PIN incorreto (${deviceName.ifBlank { "aparelho sem nome" }})")
                replyError(output, "PIN incorreto")
                return
            }

            CastProtocol.write(output, CastProtocol.TYPE_OK, ByteArray(0))
            // Sem timeout durante a transmissao: um video parado nao significa
            // conexao morta.
            client.soTimeout = 0
            connected = true
            onState(true, deviceName.ifBlank { "Celular" })

            while (running) {
                val message = CastProtocol.read(input) ?: break
                when (message.type) {
                    CastProtocol.TYPE_CONFIG ->
                        CastProtocol.parseConfig(message.payload)?.let { (w, h, csd) ->
                            sink.onConfig(w, h, csd)
                        }

                    CastProtocol.TYPE_VIDEO ->
                        CastProtocol.parseVideo(message.payload)?.let { (pts, data) ->
                            sink.onVideo(data, pts)
                        }

                    CastProtocol.TYPE_AUDIO_CONFIG ->
                        CastProtocol.parseAudioConfig(message.payload)?.let { (rate, channels, csd) ->
                            sink.onAudioConfig(rate, channels, csd)
                        }

                    CastProtocol.TYPE_AUDIO ->
                        CastProtocol.parseVideo(message.payload)?.let { (pts, data) ->
                            sink.onAudio(data, pts)
                        }

                    CastProtocol.TYPE_BYE -> return
                }
            }
        } catch (e: IOException) {
            // Queda de rede / celular fechando o app: encerra esta conexao.
            onLog("conexao encerrada: ${e.message}")
        } finally {
            runCatching { client.close() }
            clientSocket = null
            if (connected) onState(false, null)
        }
    }

    private fun replyError(output: DataOutputStream, message: String) {
        runCatching {
            CastProtocol.write(
                output,
                CastProtocol.TYPE_ERROR,
                message.toByteArray(Charsets.UTF_8),
            )
        }
    }

    fun stop() {
        onLog("fechando servidor")
        running = false
        runCatching { clientSocket?.close() }
        clientSocket = null
        runCatching { serverSocket?.close() }
        serverSocket = null
        runCatching { acceptThread?.join(500) }
        acceptThread = null
    }

    private companion object {
        const val HANDSHAKE_TIMEOUT_MS = 15_000
    }
}
