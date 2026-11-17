package com.eftv.android.cast

import android.media.MediaCodec
import android.media.MediaFormat
import android.view.Surface
import java.nio.ByteBuffer
import java.util.concurrent.ArrayBlockingQueue
import java.util.concurrent.TimeUnit

/**
 * Decodifica o H.264 que chega do celular e desenha direto na Surface da tela.
 *
 * Usa o decodificador de hardware do aparelho (`MediaCodec`), sem ExoPlayer:
 * o stream nao tem container (MP4/TS), sao amostras cruas do encoder do outro
 * lado do socket.
 */
class H264Decoder(
    private val surface: Surface,
    private val onError: (String) -> Unit,
) {

    private data class Frame(val data: ByteArray, val ptsUs: Long)

    /** Fila curta: se a TV atrasar, descartar e melhor que acumular segundos. */
    private val queue = ArrayBlockingQueue<Frame>(QUEUE_SIZE)

    @Volatile
    private var codec: MediaCodec? = null

    @Volatile
    private var running = false

    private var thread: Thread? = null

    @Volatile
    var width: Int = 0
        private set

    @Volatile
    var height: Int = 0
        private set

    /** Abre (ou reabre) o decodificador. Pode ser chamado a cada CONFIG. */
    @Synchronized
    fun configure(w: Int, h: Int, csd: ByteArray) {
        release()
        try {
            val format = MediaFormat.createVideoFormat(MediaFormat.MIMETYPE_VIDEO_AVC, w, h)
            format.setByteBuffer("csd-0", ByteBuffer.wrap(csd))
            val decoder = MediaCodec.createDecoderByType(MediaFormat.MIMETYPE_VIDEO_AVC)
            decoder.configure(format, surface, null, 0)
            decoder.start()
            codec = decoder
            width = w
            height = h
            queue.clear()
            running = true
            thread = Thread({ decodeLoop() }, "eftv-cast-decode").apply {
                priority = Thread.MAX_PRIORITY
                start()
            }
        } catch (e: Exception) {
            running = false
            onError(e.message ?: "Falha ao abrir o video")
        }
    }

    /** Enfileira uma amostra vinda da rede. Antes do CONFIG, e ignorada. */
    fun video(data: ByteArray, ptsUs: Long) {
        if (!running) return
        val frame = Frame(data, ptsUs)
        if (!queue.offer(frame)) {
            // Fila cheia: joga fora a amostra mais antiga para nao atrasar.
            queue.poll()
            queue.offer(frame)
        }
    }

    private fun decodeLoop() {
        val info = MediaCodec.BufferInfo()
        while (running) {
            val decoder = codec ?: break
            try {
                val frame = queue.poll(200, TimeUnit.MILLISECONDS)
                if (frame != null) {
                    feed(decoder, frame)
                }
                drain(decoder, info)
            } catch (e: IllegalStateException) {
                if (running) onError(e.message ?: "O decodificador parou")
                break
            } catch (e: Exception) {
                if (running) onError(e.message ?: "Falha ao decodificar")
                break
            }
        }
    }

    private fun feed(decoder: MediaCodec, frame: Frame) {
        val index = decoder.dequeueInputBuffer(10_000)
        if (index < 0) return
        val buffer = decoder.getInputBuffer(index)
        if (buffer == null) {
            decoder.queueInputBuffer(index, 0, 0, frame.ptsUs, 0)
            return
        }
        buffer.clear()
        buffer.put(frame.data)
        decoder.queueInputBuffer(index, 0, frame.data.size, frame.ptsUs, 0)
    }

    private fun drain(decoder: MediaCodec, info: MediaCodec.BufferInfo) {
        var index = decoder.dequeueOutputBuffer(info, 0)
        while (index >= 0) {
            // `true` entrega o quadro para a Surface imediatamente.
            decoder.releaseOutputBuffer(index, true)
            index = decoder.dequeueOutputBuffer(info, 0)
        }
    }

    /** Encerra o decodificador e a thread. Seguro chamar mais de uma vez. */
    @Synchronized
    fun release() {
        running = false
        queue.clear()
        runCatching { thread?.join(400) }
        thread = null
        val decoder = codec
        codec = null
        if (decoder != null) {
            runCatching { decoder.stop() }
            runCatching { decoder.release() }
        }
    }

    private companion object {
        const val QUEUE_SIZE = 10
    }
}
