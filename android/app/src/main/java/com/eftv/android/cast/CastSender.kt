package com.eftv.android.cast

import android.content.Context
import android.hardware.display.DisplayManager
import android.hardware.display.VirtualDisplay
import android.media.AudioAttributes
import android.media.AudioFormat
import android.media.AudioPlaybackCaptureConfiguration
import android.media.AudioRecord
import android.media.MediaCodec
import android.media.MediaCodecInfo
import android.media.MediaFormat
import android.media.projection.MediaProjection
import android.os.Build
import android.os.Handler
import android.os.HandlerThread
import android.view.Surface
import androidx.annotation.RequiresApi
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
import kotlin.math.abs
import timber.log.Timber

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
    private val withAudio: Boolean,
    private val onStatus: (CastStatus) -> Unit,
) {

    @Volatile
    private var running = false

    /**
     * True quando a limpeza partiu do proprio app (erro, botao Parar, servico
     * encerrando). Serve para o servico nao confundir a queda da projecao que
     * ele mesmo pediu com uma captura interrompida pelo sistema.
     */
    @Volatile
    var isStopping = false
        private set

    private var socket: Socket? = null
    private var codec: MediaCodec? = null
    private var inputSurface: Surface? = null
    private var virtualDisplay: VirtualDisplay? = null
    private var projectionThread: HandlerThread? = null
    private var encoderWidth = 0
    private var encoderHeight = 0

    private var audioRecord: AudioRecord? = null
    private var audioCodec: MediaCodec? = null
    private var audioThread: Thread? = null

    @Volatile
    private var audioRunning = false

    /**
     * Diferenca entre o relogio das amostras de video (vem do encoder, baseado
     * no timestamp das telas) e o `System.nanoTime()` usado para carimbar o
     * som. Normalmente e zero: os dois vem do mesmo relogio monotonico do
     * Android. So e diferente se o aparelho usar outra base, e nesse caso o
     * som precisa do mesmo deslocamento para a TV alinhar as trilhas.
     */
    @Volatile
    private var audioBaseOffsetUs = 0L

    /**
     * Video e audio saem por threads diferentes no mesmo socket. Sem esta
     * trava, duas mensagens poderiam se entrelaçar e corromper o stream.
     */
    private val writeLock = Any()

    private fun send(output: DataOutputStream, type: Int, payload: ByteArray) {
        synchronized(writeLock) {
            CastProtocol.write(output, type, payload)
        }
    }

    fun start() {
        if (running) return
        running = true
        thread(name = "eftv-cast-sender", isDaemon = true) { runSession() }
    }

    private fun runSession() {
        var failure: String? = null
        try {
            onStatus(CastStatus(CastStatus.State.CONNECTING, "Conectando a $host…"))
            Timber.i("Cast: conectando a %s:%d", host, port)
            val connection = Socket().apply {
                tcpNoDelay = true
                connect(InetSocketAddress(host, port), CONNECT_TIMEOUT_MS)
            }
            socket = connection
            Timber.i("Cast: conectado")

            val output = DataOutputStream(
                BufferedOutputStream(connection.getOutputStream(), 256 * 1024),
            )
            val input = DataInputStream(
                BufferedInputStream(connection.getInputStream(), 4 * 1024),
            )

            send(
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
            Timber.w(e, "Cast: falhou (%s)", failure)
        } finally {
            // Se a parada partiu do servico/botao, o estado final e dele.
            val stoppedByUs = isStopping
            cleanup()
            if (!stoppedByUs) {
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
        val display = projection.createVirtualDisplay(
            "eftv-cast",
            width,
            height,
            dpi,
            DisplayManager.VIRTUAL_DISPLAY_FLAG_AUTO_MIRROR,
            surface,
            null,
            Handler(handlerThread.looper),
        )
        virtualDisplay = display
        Timber.i("Cast: captura %dx%d, display %s", width, height, display != null)

        onStatus(CastStatus(CastStatus.State.STREAMING, "Transmitindo para a TV"))
        // O audio so comeca depois do primeiro quadro: ai ja se sabe a base de
        // tempo do video e o som entra carimbado no mesmo relogio.
        drainEncoder(encoder, output)
    }

    /**
     * Captura o som que o proprio Android esta tocando (nao o microfone) via
     * `AudioPlaybackCaptureConfiguration`. Só existe no Android 10+ e depende
     * da permissao RECORD_AUDIO; sem ela, a transmissao segue so com a imagem.
     */
    @RequiresApi(Build.VERSION_CODES.Q)
    private fun startAudio(output: DataOutputStream) {
        try {
            val capture = AudioPlaybackCaptureConfiguration.Builder(projection)
                .addMatchingUsage(AudioAttributes.USAGE_MEDIA)
                .addMatchingUsage(AudioAttributes.USAGE_GAME)
                .addMatchingUsage(AudioAttributes.USAGE_UNKNOWN)
                .build()
            val audioFormat = AudioFormat.Builder()
                .setEncoding(AudioFormat.ENCODING_PCM_16BIT)
                .setSampleRate(AUDIO_SAMPLE_RATE)
                .setChannelMask(AudioFormat.CHANNEL_IN_STEREO)
                .build()
            val minBuffer = AudioRecord.getMinBufferSize(
                AUDIO_SAMPLE_RATE,
                AudioFormat.CHANNEL_IN_STEREO,
                AudioFormat.ENCODING_PCM_16BIT,
            )
            val record = AudioRecord.Builder()
                .setAudioFormat(audioFormat)
                .setBufferSizeInBytes(minBuffer.coerceAtLeast(4_096) * 2)
                .setAudioPlaybackCaptureConfig(capture)
                .build()
            if (record.state != AudioRecord.STATE_INITIALIZED) {
                record.release()
                return
            }

            val encoderFormat = MediaFormat.createAudioFormat(
                MediaFormat.MIMETYPE_AUDIO_AAC,
                AUDIO_SAMPLE_RATE,
                AUDIO_CHANNELS,
            )
            encoderFormat.setInteger(
                MediaFormat.KEY_AAC_PROFILE,
                MediaCodecInfo.CodecProfileLevel.AACObjectLC,
            )
            encoderFormat.setInteger(MediaFormat.KEY_BIT_RATE, AUDIO_BIT_RATE)
            encoderFormat.setInteger(MediaFormat.KEY_MAX_INPUT_SIZE, 16_384)

            val encoder = MediaCodec.createEncoderByType(MediaFormat.MIMETYPE_AUDIO_AAC)
            encoder.configure(encoderFormat, null, null, MediaCodec.CONFIGURE_FLAG_ENCODE)
            encoder.start()
            record.startRecording()

            audioRecord = record
            audioCodec = encoder
            audioRunning = true
            audioThread = thread(name = "eftv-cast-audio-send", isDaemon = true) {
                audioLoop(record, encoder, output)
            }
        } catch (e: Exception) {
            // Sem permissao, aparelho sem captura de som ou encoder ocupado:
            // o video continua; o cliente so nao ouve.
            audioRunning = false
            runCatching { audioRecord?.release() }
            audioRecord = null
            runCatching { audioCodec?.release() }
            audioCodec = null
        }
    }

    private fun audioLoop(record: AudioRecord, encoder: MediaCodec, output: DataOutputStream) {
        // 4096 bytes ≈ 23 ms de PCM estereo 16-bit: um frame AAC.
        val pcm = ByteArray(4_096)
        val info = MediaCodec.BufferInfo()
        val bytesPerSecond = AUDIO_SAMPLE_RATE * AUDIO_CHANNELS * 2
        var configSent = false
        // Carimbo do primeiro PCM lido, no relogio comum das duas trilhas.
        var ptsUs = 0L

        while (audioRunning && running) {
            val startNs = System.nanoTime()
            val read = runCatching { record.read(pcm, 0, pcm.size) }.getOrDefault(-1)
            if (read <= 0) continue

            val durationUs = read * 1_000_000L / bytesPerSecond
            if (ptsUs == 0L) {
                // O primeiro byte do bloco foi capturado `durationUs` atras.
                ptsUs = startNs / 1_000L - durationUs + audioBaseOffsetUs
            }

            val inputIndex = encoder.dequeueInputBuffer(10_000)
            if (inputIndex >= 0) {
                val buffer = encoder.getInputBuffer(inputIndex)
                if (buffer != null) {
                    buffer.clear()
                    buffer.put(pcm, 0, read)
                    encoder.queueInputBuffer(inputIndex, 0, read, ptsUs, 0)
                } else {
                    encoder.queueInputBuffer(inputIndex, 0, 0, ptsUs, 0)
                }
            }
            // O bloco seguinte comeca onde este terminou (contagem de amostras,
            // nao relogio: assim o som nao escorrega se a thread atrasar).
            ptsUs += durationUs

            var outputIndex = encoder.dequeueOutputBuffer(info, 0)
            while (outputIndex >= 0) {
                val buffer = encoder.getOutputBuffer(outputIndex)
                if (buffer != null && info.size > 0) {
                    buffer.position(info.offset)
                    buffer.limit(info.offset + info.size)
                    if (info.flags and MediaCodec.BUFFER_FLAG_CODEC_CONFIG != 0) {
                        if (!configSent) configSent = sendAudioConfig(output, buffer)
                    } else if (configSent) {
                        val data = ByteArray(info.size)
                        buffer.get(data)
                        send(
                            output,
                            CastProtocol.TYPE_AUDIO,
                            CastProtocol.videoPayload(info.presentationTimeUs, data),
                        )
                    }
                }
                encoder.releaseOutputBuffer(outputIndex, false)
                outputIndex = encoder.dequeueOutputBuffer(info, 0)
            }
        }
    }

    private fun sendAudioConfig(output: DataOutputStream, csd: java.nio.ByteBuffer): Boolean = try {
        val data = ByteArray(csd.remaining())
        csd.get(data)
        send(
            output,
            CastProtocol.TYPE_AUDIO_CONFIG,
            CastProtocol.audioConfigPayload(AUDIO_SAMPLE_RATE, AUDIO_CHANNELS, data),
        )
        true
    } catch (_: IOException) {
        false
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
        var audioStarted = false

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
                        send(
                            output,
                            CastProtocol.TYPE_VIDEO,
                            CastProtocol.videoPayload(info.presentationTimeUs, data),
                        )
                        if (!audioStarted) {
                            // Primeiro quadro a caminho: agora existe uma base de
                            // tempo de video para o som se alinhar.
                            audioStarted = true
                            if (withAudio && Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                                audioBaseOffsetUs = clockOffsetFor(info.presentationTimeUs)
                                startAudio(output)
                            }
                        }
                    }
                }
                encoder.releaseOutputBuffer(index, false)
            }
        }
    }

    /**
     * Descobre quanto o carimbo do video esta deslocado do `System.nanoTime()`.
     *
     * O plano normal e zero: o encoder usa o timestamp das telas, que vem do
     * mesmo relogio monotonico. A medida no primeiro quadro, porem, carrega a
     * latencia do encoder (dezenas de ms de atraso entre capturar e sair), e
     * corrigir por ela deixaria o som adiantado. Por isso so vale um
     * deslocamento grande — sinal de que o aparelho usa outra base de tempo.
     */
    private fun clockOffsetFor(videoPtsUs: Long): Long {
        val guess = videoPtsUs - System.nanoTime() / 1_000L
        return if (abs(guess) > CLOCK_MISMATCH_US) guess else 0L
    }

    private fun sendConfig(output: DataOutputStream, csd: java.nio.ByteBuffer): Boolean {
        val data = ByteArray(csd.remaining())
        csd.get(data)
        send(
            output,
            CastProtocol.TYPE_CONFIG,
            CastProtocol.configPayload(encoderWidth, encoderHeight, data),
        )
        return true
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
        isStopping = true
        stopAudio()

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

    private fun stopAudio() {
        audioRunning = false
        runCatching { audioRecord?.stop() }
        runCatching { audioThread?.join(400) }
        audioThread = null
        runCatching { audioRecord?.release() }
        audioRecord = null
        runCatching { audioCodec?.stop() }
        runCatching { audioCodec?.release() }
        audioCodec = null
    }

    private fun friendlyMessage(e: Exception): String = when (e) {
        is UnknownHostException -> "TV não encontrada na rede"
        is ConnectException, is NoRouteToHostException ->
            "Não foi possível conectar. Confira se o celular e a TV estão no mesmo Wi-Fi"

        is SocketTimeoutException -> "A TV demorou para responder"
        is IOException -> "A conexão com a TV caiu"
        else -> e.message ?: "Falha na transmissão"
    }

    private companion object {
        const val CONNECT_TIMEOUT_MS = 8_000
        const val MAX_WIDTH = 1280
        const val MAX_HEIGHT = 720
        const val BIT_RATE = 4_000_000
        const val FRAME_RATE = 30

        /** Som: estereo 44,1 kHz a 128 kbps — suficiente para TV. */
        const val AUDIO_SAMPLE_RATE = 44_100
        const val AUDIO_CHANNELS = 2
        const val AUDIO_BIT_RATE = 128_000

        /**
         * Diferenca de relogio que so pode ser troca de base de tempo (segundos
         * ou mais), nunca latencia. Abaixo disso, assumimos base igual.
         */
        const val CLOCK_MISMATCH_US = 2_000_000L
    }
}
