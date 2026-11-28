package com.eftv.android.data

import androidx.media3.common.MimeTypes
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class PlaybackSupportTest {

    @Test
    fun `m3u8 usa MIME de HLS mesmo com query`() {
        assertEquals(
            MimeTypes.APPLICATION_M3U8,
            PlaybackSupport.mimeType("https://provider.example/live/u/p/123.m3u8?token=abc"),
        )
        assertEquals(
            MimeTypes.APPLICATION_M3U8,
            PlaybackSupport.mimeType("https://provider.example/MOVIE.M3U"),
        )
    }

    @Test
    fun `mpd ts mp4 mkv e webm tem MIME proprio`() {
        assertEquals(MimeTypes.APPLICATION_MPD, PlaybackSupport.mimeType("http://x/a.mpd"))
        assertEquals(MimeTypes.VIDEO_MP2T, PlaybackSupport.mimeType("http://x/a.ts"))
        assertEquals(MimeTypes.VIDEO_MP4, PlaybackSupport.mimeType("http://x/a.mp4"))
        assertEquals(MimeTypes.VIDEO_MATROSKA, PlaybackSupport.mimeType("http://x/a.mkv"))
        assertEquals(MimeTypes.VIDEO_WEBM, PlaybackSupport.mimeType("http://x/a.webm"))
        assertEquals(MimeTypes.APPLICATION_RTSP, PlaybackSupport.mimeType("rtsp://x/a"))
    }

    @Test
    fun `url sem extensao fica sem MIME para o player tentar progressivo`() {
        assertNull(PlaybackSupport.mimeType("http://x/live/u/p/12345"))
        assertNull(PlaybackSupport.mimeType("http://x/movie/u/p/987"))
    }

    @Test
    fun `extensao desconhecida nao e confundida com a query`() {
        assertEquals("mkv", PlaybackSupport.extension("http://x/filme.mkv?token=1#t=10"))
        assertEquals("", PlaybackSupport.extension("http://x/stream?file=filme.avi"))
    }

    @Test
    fun `containers sem suporte sao detectados`() {
        assertTrue(PlaybackSupport.isUnsupportedContainer("http://x/filme.avi"))
        assertTrue(PlaybackSupport.isUnsupportedContainer("http://x/filme.WMV?x=1"))
        assertTrue(PlaybackSupport.isUnsupportedContainer("http://x/filme.rmvb"))
        assertFalse(PlaybackSupport.isUnsupportedContainer("http://x/filme.mkv"))
        assertFalse(PlaybackSupport.isUnsupportedContainer("http://x/filme.mp4"))
        assertFalse(PlaybackSupport.isUnsupportedContainer("http://x/canal.ts"))
    }

    @Test
    fun `protocolos sem suporte sao detectados`() {
        assertTrue(PlaybackSupport.isUnsupportedProtocol("rtmp://x/live"))
        assertTrue(PlaybackSupport.isUnsupportedProtocol("udp://239.0.0.1:1234"))
        assertTrue(PlaybackSupport.isUnsupportedProtocol("mms://x/a"))
        assertFalse(PlaybackSupport.isUnsupportedProtocol("rtsp://x/a"))
        assertFalse(PlaybackSupport.isUnsupportedProtocol("https://x/a.m3u8"))
    }

    @Test
    fun `proxy e preferido no celular e no VPN`() {
        assertTrue(PlaybackSupport.preferProxy("movel"))
        assertTrue(PlaybackSupport.preferProxy("vpn"))
        assertFalse(PlaybackSupport.preferProxy("wifi"))
        assertFalse(PlaybackSupport.preferProxy("ethernet"))
        assertFalse(PlaybackSupport.preferProxy("offline"))
    }

    @Test
    fun `erros de rede e parsing justificam trocar de fonte`() {
        assertTrue(
            PlaybackSupport.sourceFallbackWorthy(
                androidx.media3.common.PlaybackException.ERROR_CODE_IO_NETWORK_CONNECTION_TIMEOUT,
            ),
        )
        assertTrue(
            PlaybackSupport.sourceFallbackWorthy(
                androidx.media3.common.PlaybackException.ERROR_CODE_PARSING_CONTAINER_UNSUPPORTED,
            ),
        )
        assertFalse(
            PlaybackSupport.sourceFallbackWorthy(
                androidx.media3.common.PlaybackException.ERROR_CODE_DECODING_FORMAT_UNSUPPORTED,
            ),
        )
        assertFalse(
            PlaybackSupport.sourceFallbackWorthy(
                androidx.media3.common.PlaybackException.ERROR_CODE_DRM_LICENSE_EXPIRED,
            ),
        )
    }

    @Test
    fun `parsing justifica tentar HLS e decoder e erro definitivo`() {
        assertTrue(
            PlaybackSupport.containerFallbackWorthy(
                androidx.media3.common.PlaybackException.ERROR_CODE_PARSING_MANIFEST_MALFORMED,
            ),
        )
        assertFalse(
            PlaybackSupport.containerFallbackWorthy(
                androidx.media3.common.PlaybackException.ERROR_CODE_IO_NETWORK_CONNECTION_FAILED,
            ),
        )
        assertTrue(
            PlaybackSupport.isDecoderError(
                androidx.media3.common.PlaybackException.ERROR_CODE_DECODING_FORMAT_UNSUPPORTED,
            ),
        )
        assertTrue(
            PlaybackSupport.isDecoderError(
                androidx.media3.common.PlaybackException.ERROR_CODE_DECODER_INIT_FAILED,
            ),
        )
        assertFalse(
            PlaybackSupport.isDecoderError(
                androidx.media3.common.PlaybackException.ERROR_CODE_IO_NETWORK_CONNECTION_FAILED,
            ),
        )
    }
}
