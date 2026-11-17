package com.eftv.android.cast

import android.content.Context
import android.hardware.display.DisplayManager
import android.hardware.display.VirtualDisplay
import android.media.MediaCodec
import android.media.MediaCodecInfo
import android.media.MediaFormat
import android.media.projection.MediaProjection
import android.os.Build
import android.os.Handler
import android.os.HandlerThread
import android.view.Surface
import java.io.BufferedInputStream
import java.io.BufferedOutputStream
import java.io.DataInputStream
import java.io.DataOutputStream
import java.io.IOException
import java.net.ConnectException
import java.net.InetSocketAddress
import java.net.NoRouteToHostException
import java.net.Socket
import java.net.SocketTimeoutException
import java.net.UnknownHostException
import kotlin.concurrent.thread

/**
 * Lado do celular: captura a tela inteira e envia para a TV.
 *
 * Fluxo:
 * 1. conecta no socket da TV e apresenta o PIN;
 * 2. cria o encoder H.264 em cima de uma Surface (nada de ler pixels);
 * 3. espelha a tela para essa Surface com `MediaProjection`;
 * 4. manda SPS/PPS (CONFIG) e depois cada access unit (VIDEO).
 *
 * Quem chama precisa manter um servico em primeiro plano: no Android 14 a
 * captura de tela so continua com o app em segundo plano se houver
 * `foregroundServiceType="mediaProjection"`.
 */
class CastSender(
    private val context: Context,
    private val projection: MediaProjection,
    private val host: String,
    private val port: Int,
    private val pin: String,
    private val onStatus: (CastStatus) -> Unit,
) {

    @Volatile
    private var running = false

    private var socket: Socket? = null
    private var codec: MediaCodec? = null
    private var inputSurface: Surface? = null
    private var virtualDisplay: VirtualDisplay? = null
    private var projectionThread: HandlerThread? = null
    private var encoderWidth = 0
    private var encoderHeight = 0

    fun start() {
        if (running) return
        running = true
        thread(name = "eftv-cast-sender", isDaemon = true) { runSession() }
    }

    private fun runSession() {
        var failure: String? = null
        try {
            onStatus(CastStatus(CastStatus.State.CONNECTING, "Conectando a $host…"))
            val connection = Socket().apply {
                tcpNoDelay = true
                connect(InetSocketAddress(host, port), CONNECT_TIMEOUT_MS)
            }
            socket = connection

            val output = DataOutputStream(
                BufferedOutputStream(connection.getOutputStream(), 256 * 1024),
            )
            val input = DataInputStream(
                BufferedInputStream(connection.getInputStream(), 4 * 1024),
            )

            CastProtocol.write(
                output,
                CastProtocol.TYPE_HELLO,
                CastProtocol.helloPayload(pin, Build.MODEL),
            )
            when (val reply = CastProtocol.read(input)) {
                null -> throw IOException("A TV não respondeu")
                else -> when (reply.type) {
                    CastProtocol.TYPE_OK -> Unit
                    CastProtocol.TYPE_ERROR -> throw IOException(
                        reply.payload.toString(Charsets.UTF_8).ifBlank { "A TV recusou a conexão" },
                    )

                    else -> throw IOException("Resposta inesperada da TV")
                }
            }

            startCapture(output)
        } catch (e: Exception) {
            failure = friendlyMessage(e)
        } finally {
            cleanup()
            if (running) {
                running = false
                onStatus(
                    if (failure != null) {
                        CastStatus(CastStatus.State.ERROR, failure)
                    } else {
                        CastStatus(CastStatus.State.IDLE, "Transmissão encerrada")
                    },
                )
            }
        }
    }

    /**
     * Liga o encoder e o espelhamento da tela. Fica no laco de drenagem ate a
     * transmissao acabar (usuario parou, TV fechou ou a rede caiu).
     */
    private fun startCapture(output: DataOutputStream) {
        val (width, height) = captureSize()
        val dpi = context.resources.displayMetrics.densityDpi

        val format = MediaFormat.createVideoFormat(MediaFormat.MIMETYPE_VIDEO_AVC, width, height)
        format.setInteger(
            MediaFormat.KEY_COLOR_FORMAT,
            MediaCodecInfo.CodecCapabilities.COLOR_FormatSurface,
        )
        format.setInteger(MediaFormat.KEY_BIT_RATE, BIT_RATE)
        format.setInteger(MediaFormat.KEY_FRAME_RATE, FRAME_RATE)
        // Keyframe de 1 em 1 segundo: quem entra no meio espera no maximo isso.
        format.setInteger(MediaFormat.KEY_I_FRAME_INTERVAL, 1)
        // Nem todo encoder aceita CBR; se recusar, o padrao do aparelho serve.
        runCatching {
            format.setInteger(
                MediaFormat.KEY_BITRATE_MODE,
                MediaCodecInfo.EncoderCapabilities.BITRATE_MODE_CBR,
            )
        }

        val encoder = MediaCodec.createEncoderByType(MediaFormat.MIMETYPE_VIDEO_AVC)
        encoder.configure(format, null, null, MediaCodec.CONFIGURE_FLAG_ENCODE)
        val surface = encoder.createInputSurface()
        encoder.start()
        codec = encoder
        inputSurface = surface

        val handlerThread = HandlerThread("eftv-cast-projection").apply { start() }
        projectionThread = handlerThread
        virtualDisplay = projection.createVirtualDisplay(
            "eftv-cast",
            width,
            height,
            dpi,
            DisplayManager.VIRTUAL_DISPLAY_FLAG_AUTO_MIRROR,
            surface,
            null,
            Handler(handlerThread.looper),
        )

        onStatus(CastStatus(CastStatus.State.STREAMING, "Transmitindo para a TV"))
        drainEncoder(encoder, output)
    }

    /**
     * Espelha no maximo 720p: a TV nao ganha nada com 1080p e a rede Wi-Fi
     * domestica sofre com 8 Mbps de subida. Largura e altura multiplas de 16
     * porque alguns encoders recusam valores quebrados.
     */
    private fun captureSize(): Pair<Int, Int> {
        val metrics = context.resources.displayMetrics
        var width = metrics.widthPixels
        var height = metrics.heightPixels
        if (width <= 0 || height <= 0) throw IOException("Tela indisponível")

        if (width > MAX_WIDTH) {
            height = (height.toLong() * MAX_WIDTH / width).toInt()
            width = MAX_WIDTH
        }
        if (height > MAX_HEIGHT) {
            width = (width.toLong() * MAX_HEIGHT / height).toInt()
            height = MAX_HEIGHT
        }
        width = (width.coerceAtLeast(16) / 16) * 16
        height = (height.coerceAtLeast(16) / 16) * 16
        encoderWidth = width
        encoderHeight = height
        return width to height
    }

    private fun drainEncoder(encoder: MediaCodec, output: DataOutputStream) {
        val info = MediaCodec.BufferInfo()
        var configSent = false

        while (running) {
            val index = encoder.dequeueOutputBuffer(info, 10_000)
            if (index == MediaCodec.INFO_OUTPUT_FORMAT_CHANGED) {
                val csd = encoder.outputFormat.getByteBuffer("csd-0")
                if (csd != null) {
                    configSent = sendConfig(output, csd)
                }
            } else if (index >= 0) {
                val buffer = encoder.getOutputBuffer(index)
                if (buffer != null && info.size > 0) {
                    buffer.position(info.offset)
                    buffer.limit(info.offset + info.size)
                    val isConfig = info.flags and MediaCodec.BUFFER_FLAG_CODEC_CONFIG != 0
                    if (isConfig) {
                        if (!configSent) configSent = sendConfig(output, buffer)
                    } else if (configSent) {
                        val data = ByteArray(info.size)
                        buffer.get(data)
                        CastProtocol.write(
                            output,
                            CastProtocol.TYPE_VIDEO,
                            CastProtocol.videoPayload(info.presentationTimeUs, data),
                        )
                    }
                }
                encoder.releaseOutputBuffer(index, false)
            }
        }
    }

    private fun sendConfig(output: DataOutputStream, csd: java.nio.ByteBuffer): Boolean = try {
        val data = ByteArray(csd.remaining())
        csd.get(data)
        CastProtocol.write(
            output,
            CastProtocol.TYPE_CONFIG,
            CastProtocol.configPayload(encoderWidth, encoderHeight, data),
        )
        true
    } catch (_: IOException) {
        running = false
        false
    }

    /** Encerra a transmissao (chamado pelo servico ou pelo botao Parar). */
    @Synchronized
    fun stop() {
        if (!running && socket == null && codec == null) return
        running = false
        cleanup()
    }

    @Synchronized
    private fun cleanup() {
        runCatching { virtualDisplay?.release() }
        virtualDisplay = null
        runCatching { inputSurface?.release() }
        inputSurface = null

        val encoder = codec
        codec = null
        if (encoder != null) {
            runCatching { encoder.stop() }
            runCatching { encoder.release() }
        }

        runCatching { socket?.close() }
        socket = null
        runCatching { projectionThread?.quitSafely() }
        projectionThread = null
        // Depois disso o Android derruba a barra de "gravando a tela".
        runCatching { projection.stop() }
    }

    private fun friendlyMessage(e: Exception): String = when (e) {
        is UnknownHostException -> "TV não encontrada na rede"
        is ConnectException, is NoRouteToHostException ->
            "Não foi possível conectar. Confira se o celular e a TV estão no mesmo Wi-Fi"

        is SocketTimeoutException -> "A TV demorou para responder"
        else -> e.message ?: "Falha na transmissão"
    }

    private companion object {
        const val CONNECT_TIMEOUT_MS = 8_000
        const val MAX_WIDTH = 1280
        const val MAX_HEIGHT = 720
        const val BIT_RATE = 4_000_000
        const val FRAME_RATE = 30
    }
}
