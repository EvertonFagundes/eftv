package com.eftv.android.cast

import java.io.DataInputStream
import java.io.DataOutputStream
import java.io.EOFException
import java.io.IOException

/**
 * Protocolo da transmissao de tela celular -> TV, pela rede local.
 *
 * Nao usa Miracast nem Chromecast: o proprio app captura a tela com
 * `MediaProjection`, codifica em H.264 e envia as amostras por TCP. Por isso
 * funciona em qualquer Android 5.0+, inclusive nos aparelhos que nao tem a
 * opcao "Transmitir tela" nas configuracoes (muitos TV boxes e Androids
 * antigos).
 *
 * Cada mensagem tem o formato: `[1 byte tipo][4 bytes tamanho][payload]`.
 *
 * - HELLO: `pin` + `\n` + nome do aparelho (primeira mensagem do celular)
 * - OK / ERROR: resposta da TV (ERROR traz o motivo em UTF-8)
 * - CONFIG: largura (2 bytes) + altura (2 bytes) + SPS/PPS em Annex-B
 * - VIDEO: timestamp em microssegundos (8 bytes) + um access unit H.264
 * - BYE: encerramento educado
 *
 * O CONFIG sempre vem antes dos videos: e o que permite o decodificador da TV
 * abrir a imagem sem depender do que ja passou.
 */
object CastProtocol {

    /** Tipo de servico mDNS/NSD anunciado pela TV. */
    const val SERVICE_TYPE = "_eftvcast._tcp"

    /** Porta preferida; se estiver ocupada, a TV escolhe outra (porta 0). */
    const val DEFAULT_PORT = 8765

    const val TYPE_HELLO = 1
    const val TYPE_CONFIG = 2
    const val TYPE_VIDEO = 3
    const val TYPE_BYE = 4
    const val TYPE_OK = 5
    const val TYPE_ERROR = 6

    /** Teto de seguranca: um access unit 1080p raramente passa de 1 MB. */
    private const val MAX_PAYLOAD = 8 * 1024 * 1024

    data class Message(val type: Int, val payload: ByteArray)

    fun write(out: DataOutputStream, type: Int, payload: ByteArray) {
        out.writeByte(type)
        out.writeInt(payload.size)
        out.write(payload)
        out.flush()
    }

    /** Le uma mensagem; devolve null quando a TV/celular fechou a conexao. */
    fun read(input: DataInputStream): Message? = try {
        val type = input.readUnsignedByte()
        val size = input.readInt()
        if (size < 0 || size > MAX_PAYLOAD) throw IOException("mensagem invalida ($size bytes)")
        val payload = ByteArray(size)
        input.readFully(payload)
        Message(type, payload)
    } catch (_: EOFException) {
        null
    }

    fun helloPayload(pin: String, deviceName: String): ByteArray =
        "$pin\n${deviceName.take(60)}".toByteArray(Charsets.UTF_8)

    /** Devolve (pin, nome) ou null quando a mensagem nao e um HELLO valido. */
    fun parseHello(payload: ByteArray): Pair<String, String>? {
        val text = payload.toString(Charsets.UTF_8)
        val pin = text.substringBefore('\n').trim()
        if (pin.length < 4) return null
        return pin to text.substringAfter('\n', "").trim()
    }

    fun configPayload(width: Int, height: Int, csd: ByteArray): ByteArray {
        val out = java.io.ByteArrayOutputStream(4 + csd.size)
        val data = DataOutputStream(out)
        data.writeShort(width)
        data.writeShort(height)
        data.write(csd)
        data.flush()
        return out.toByteArray()
    }

    /** Devolve (largura, altura, SPS/PPS) ou null quando o CONFIG e invalido. */
    fun parseConfig(payload: ByteArray): Triple<Int, Int, ByteArray>? {
        if (payload.size < 5) return null
        val input = DataInputStream(payload.inputStream())
        val width = input.readUnsignedShort()
        val height = input.readUnsignedShort()
        val csd = ByteArray(payload.size - 4)
        input.readFully(csd)
        if (width <= 0 || height <= 0) return null
        return Triple(width, height, csd)
    }

    fun videoPayload(ptsUs: Long, data: ByteArray): ByteArray {
        val out = ByteArray(8 + data.size)
        for (i in 0 until 8) {
            out[i] = ((ptsUs shr (56 - i * 8)) and 0xFF).toByte()
        }
        System.arraycopy(data, 0, out, 8, data.size)
        return out
    }

    /** Devolve (timestamp, amostra H.264) ou null quando o VIDEO e invalido. */
    fun parseVideo(payload: ByteArray): Pair<Long, ByteArray>? {
        if (payload.size <= 8) return null
        var pts = 0L
        for (i in 0 until 8) {
            pts = (pts shl 8) or (payload[i].toLong() and 0xFF)
        }
        val data = ByteArray(payload.size - 8)
        System.arraycopy(payload, 8, data, 0, data.size)
        return pts to data
    }

    /** Codigo de 4 digitos que a TV mostra e o celular digita. */
    fun randomPin(): String = (1000..9999).random().toString()
}
