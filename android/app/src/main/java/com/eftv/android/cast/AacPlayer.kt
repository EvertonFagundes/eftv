package com.eftv.android.cast

import android.media.AudioAttributes
import android.media.AudioFormat
import android.media.AudioTrack
import android.media.MediaCodec
import android.media.MediaFormat
import java.nio.ByteBuffer
import java.util.concurrent.ArrayBlockingQueue
import java.util.concurrent.TimeUnit

/**
 * Toca na TV o som que chega do celular.
 *
 * O celular manda AAC cru (sem container); aqui o `MediaCodec` decodifica para
 * PCM e o [AudioTrack] reproduz. A fila e curta de proposito: som atrasado e
 * pior do que um pequeno corte.
 */
class AacPlayer(
    private val sampleRate: Int,
    private val channels: Int,
    private val csd: ByteArray,
    private val clock: PresentationClock,
    private val onError: (String) -> Unit,
) {

    private data class Frame(val data: ByteArray, val ptsUs: Long)

    private val queue = ArrayBlockingQueue<Frame>(QUEUE_SIZE)

    @Volatile
    private var running = false

    @Volatile
    private var decoder: MediaCodec? = null

    @Volatile
    private var track: AudioTrack? = null

    private var thread: Thread? = null

    fun start() {
        try {
            val format = MediaFormat.createAudioFormat(
                MediaFormat.MIMETYPE_AUDIO_AAC,
                sampleRate,
                channels,
            )
            format.setByteBuffer("csd-0", ByteBuffer.wrap(csd))
            val codec = MediaCodec.createDecoderByType(MediaFormat.MIMETYPE_AUDIO_AAC)
            codec.configure(format, null, null, 0)
            codec.start()
            decoder = codec
            running = true
            thread = Thread({ loop() }, "eftv-cast-audio").apply {
                priority = Thread.MAX_PRIORITY
                start()
            }
        } catch (e: Exception) {
            onError(e.message ?: "Falha ao abrir o áudio")
        }
    }

    fun play(data: ByteArray, ptsUs: Long) {
        if (!running) return
        val frame = Frame(data, ptsUs)
        if (!queue.offer(frame)) {
            queue.poll()
            queue.offer(frame)
        }
    }

    private fun loop() {
        val info = MediaCodec.BufferInfo()
        var pending: Frame? = null

        while (running) {
            val codec = decoder ?: break
            try {
                val frame = pending ?: queue.poll(30, TimeUnit.MILLISECONDS)
                if (frame == null) {
                    drain(codec, info)
                    continue
                }
                val now = System.nanoTime()
                val scheduled = clock.schedule(frame.ptsUs, now)
                when {
                    // Chegou adiantado: segura para o som nao sair antes do video.
                    // O PREBUFFER cobre a latencia de decodificacao + AudioTrack,
                    // entao a amostra sai do alto-falante no horario do video.
                    now + PREBUFFER_NS < scheduled -> {
                        pending = frame
                        Thread.sleep(10)
                    }
                    // Atrasado demais: descarta para alcancar a imagem.
                    now - scheduled > MAX_LAG_NS -> pending = null
                    else -> {
                        pending = null
                        feed(codec, frame)
                    }
                }
                drain(codec, info)
            } catch (e: IllegalStateException) {
                if (running) onError(e.message ?: "O áudio parou")
                break
            } catch (e: Exception) {
                if (running) onError(e.message ?: "Falha ao decodificar o áudio")
                break
            }
        }
    }

    private fun feed(codec: MediaCodec, frame: Frame) {
        val index = codec.dequeueInputBuffer(10_000)
        if (index < 0) return
        val buffer = codec.getInputBuffer(index)
        if (buffer == null) {
            codec.queueInputBuffer(index, 0, 0, frame.ptsUs, 0)
            return
        }
        buffer.clear()
        buffer.put(frame.data)
        codec.queueInputBuffer(index, 0, frame.data.size, frame.ptsUs, 0)
    }

    private fun drain(codec: MediaCodec, info: MediaCodec.BufferInfo) {
        var index = codec.dequeueOutputBuffer(info, 0)
        while (index >= 0) {
            if (info.size > 0) {
                val buffer = codec.getOutputBuffer(index)
                if (buffer != null) {
                    buffer.position(info.offset)
                    buffer.limit(info.offset + info.size)
                    val pcm = ByteArray(info.size)
                    buffer.get(pcm)
                    ensureTrack(codec)?.write(pcm, 0, pcm.size)
                }
            }
            codec.releaseOutputBuffer(index, false)
            index = codec.dequeueOutputBuffer(info, 0)
        }
    }

    /** Cria o AudioTrack na primeira amostra PCM, com o formato real do codec. */
    private fun ensureTrack(codec: MediaCodec): AudioTrack? {
        track?.let { if (it.state == AudioTrack.STATE_INITIALIZED) return it }
        val rate = runCatching {
            codec.outputFormat.getInteger(MediaFormat.KEY_SAMPLE_RATE)
        }.getOrDefault(sampleRate)
        val count = runCatching {
            codec.outputFormat.getInteger(MediaFormat.KEY_CHANNEL_COUNT)
        }.getOrDefault(channels)
        val mask = if (count == 1) {
            AudioFormat.CHANNEL_OUT_MONO
        } else {
            AudioFormat.CHANNEL_OUT_STEREO
        }
        val minBuffer = AudioTrack.getMinBufferSize(rate, mask, AudioFormat.ENCODING_PCM_16BIT)
        val output = AudioTrack.Builder()
            .setAudioAttributes(
                AudioAttributes.Builder()
                    .setUsage(AudioAttributes.USAGE_MEDIA)
                    .setContentType(AudioAttributes.CONTENT_TYPE_MOVIE)
                    .build(),
            )
            .setAudioFormat(
                AudioFormat.Builder()
                    .setEncoding(AudioFormat.ENCODING_PCM_16BIT)
                    .setSampleRate(rate)
                    .setChannelMask(mask)
                    .build(),
            )
            .setBufferSizeInBytes(minBuffer.coerceAtLeast(4_096) * 2)
            .setTransferMode(AudioTrack.MODE_STREAM)
            .build()
        output.play()
        track = output
        return output
    }

    @Synchronized
    fun release() {
        running = false
        queue.clear()
        runCatching { thread?.join(400) }
        thread = null

        val output = track
        track = null
        if (output != null) {
            runCatching { output.pause() }
            runCatching { output.flush() }
            runCatching { output.stop() }
            runCatching { output.release() }
        }

        val codec = decoder
        decoder = null
        if (codec != null) {
            runCatching { codec.stop() }
            runCatching { codec.release() }
        }
    }

    private companion object {
        const val QUEUE_SIZE = 20

        /**
         * Antecedencia com que a amostra e entregue ao decodificador. Cobre a
         * latencia de decode do AAC (~20 ms) mais o buffer do AudioTrack
         * (~50-90 ms), para o som sair no horario agendado.
         */
        const val PREBUFFER_NS = 80_000_000L

        /** Som com mais de 250 ms de atraso e descartado. */
        const val MAX_LAG_NS = 250_000_000L
    }
}
