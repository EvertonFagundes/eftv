package com.eftv.android.data

import androidx.media3.common.MimeTypes
import androidx.media3.common.PlaybackException
import java.net.URI
import java.util.Locale

/**
 * Decisoes de formato e de fonte do player.
 *
 * Fica separado da Activity para poder ser testado na JVM e para o player
 * aplicar a mesma regra em todos os caminhos (direto e proxy local).
 *
 * O proxy local entrega tudo em `127.0.0.1/api/proxy?url=...`, uma URL sem
 * extensao. Sem um MIME explicito o ExoPlayer escolhe o MediaSource pela URL
 * e trata um HLS como arquivo progressivo: a tela fica preta e o canal nao
 * abre. O MIME abaixo e calculado pela URL original do provedor.
 */
object PlaybackSupport {

    /**
     * Formatos que o Media3/ExoPlayer nao desmonta. Nesses casos o melhor
     * caminho e oferecer um player externo em vez de insistir num erro que
     * nunca vai passar.
     */
    private val UNSUPPORTED_EXTENSIONS = setOf(
        "avi",
        "wmv",
        "asf",
        "rm",
        "rmvb",
        "divx",
        "xvid",
    )

    /** Protocolos sem suporte no ExoPlayer atual (RTSP tem modulo proprio). */
    private val UNSUPPORTED_SCHEMES = setOf(
        "rtmp",
        "rtmpe",
        "rtmps",
        "rtmpt",
        "mms",
        "mmsh",
        "udp",
        "rtp",
    )

    /** Extensao da URL original, sem query/fragmento. */
    fun extension(url: String): String {
        val path = runCatching { URI(url.trim()).path }.getOrNull()
            ?: url.substringBefore('?').substringBefore('#')
        return path.substringAfterLast('.', "").lowercase(Locale.ROOT)
    }

    /** Esquema da URL (`http`, `https`, `rtsp`, ...). */
    fun scheme(url: String): String {
        val value = url.trim()
        val parsed = runCatching { URI(value).scheme }.getOrNull()
        return (parsed ?: value.substringBefore(':', ""))
            .lowercase(Locale.ROOT)
    }

    /**
     * MIME que forca o MediaSource correto. `null` deixa o ExoPlayer decidir
     * pela URL (caso comum de MP4/TS sem extensao reconhecida).
     */
    fun mimeType(url: String): String? = when (extension(url)) {
        "m3u8", "m3u" -> MimeTypes.APPLICATION_M3U8
        "mpd" -> MimeTypes.APPLICATION_MPD
        "ts", "m2ts", "mts" -> MimeTypes.VIDEO_MP2T
        "mp4", "m4v", "mov" -> MimeTypes.VIDEO_MP4
        "mkv" -> MimeTypes.VIDEO_MATROSKA
        "webm" -> MimeTypes.VIDEO_WEBM
        else -> if (scheme(url) == "rtsp") MimeTypes.APPLICATION_RTSP else null
    }

    fun isUnsupportedContainer(url: String): Boolean =
        extension(url) in UNSUPPORTED_EXTENSIONS

    fun isUnsupportedProtocol(url: String): Boolean =
        scheme(url) in UNSUPPORTED_SCHEMES

    /**
     * No celular o proxy local resolve DNS da operadora via DoH; no Wi-Fi o
     * acesso direto e mais rapido e nao passa pelo processo Python.
     */
    fun preferProxy(networkLabel: String): Boolean =
        networkLabel == "movel" || networkLabel == "vpn"

    /** A falha pode ser da fonte atual: vale tentar a outra (direto <-> proxy). */
    fun sourceFallbackWorthy(errorCode: Int): Boolean = errorCode in setOf(
        PlaybackException.ERROR_CODE_IO_UNSPECIFIED,
        PlaybackException.ERROR_CODE_IO_NETWORK_CONNECTION_FAILED,
        PlaybackException.ERROR_CODE_IO_NETWORK_CONNECTION_TIMEOUT,
        PlaybackException.ERROR_CODE_IO_INVALID_HTTP_CONTENT_TYPE,
        PlaybackException.ERROR_CODE_IO_BAD_HTTP_STATUS,
        PlaybackException.ERROR_CODE_IO_FILE_NOT_FOUND,
        PlaybackException.ERROR_CODE_IO_READ_POSITION_OUT_OF_RANGE,
        PlaybackException.ERROR_CODE_PARSING_CONTAINER_MALFORMED,
        PlaybackException.ERROR_CODE_PARSING_MANIFEST_MALFORMED,
        PlaybackException.ERROR_CODE_PARSING_CONTAINER_UNSUPPORTED,
        PlaybackException.ERROR_CODE_PARSING_MANIFEST_UNSUPPORTED,
    )

    /**
     * O conteudo nao e o que a URL dizia (TS que na verdade e HLS, HTML do
     * provedor etc.). Vale tentar o manifesto HLS antes de desistir.
     */
    fun containerFallbackWorthy(errorCode: Int): Boolean = errorCode in setOf(
        PlaybackException.ERROR_CODE_IO_INVALID_HTTP_CONTENT_TYPE,
        PlaybackException.ERROR_CODE_PARSING_CONTAINER_MALFORMED,
        PlaybackException.ERROR_CODE_PARSING_MANIFEST_MALFORMED,
        PlaybackException.ERROR_CODE_PARSING_CONTAINER_UNSUPPORTED,
        PlaybackException.ERROR_CODE_PARSING_MANIFEST_UNSUPPORTED,
    )

    /** Falhas de decoder/codec nao melhoram com retry nem com proxy. */
    fun isDecoderError(errorCode: Int): Boolean = errorCode in setOf(
        PlaybackException.ERROR_CODE_DECODER_INIT_FAILED,
        PlaybackException.ERROR_CODE_DECODER_QUERY_FAILED,
        PlaybackException.ERROR_CODE_DECODING_FAILED,
        PlaybackException.ERROR_CODE_DECODING_FORMAT_EXCEEDS_CAPABILITIES,
        PlaybackException.ERROR_CODE_DECODING_FORMAT_UNSUPPORTED,
        PlaybackException.ERROR_CODE_AUDIO_TRACK_INIT_FAILED,
    )
}
