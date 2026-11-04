package com.eftv.android.data

import com.eftv.android.PlaylistConfig

/**
 * Origem do catalogo. Quando o servidor autoriza o aparelho, a URL vem do
 * backend; sem servidor, o app mantem a lista configurada no APK para nao
 * ficar inutilizavel.
 */
data class PlaylistSource(
    val url: String,
    val userAgent: String,
    val referer: String? = null,
    val fromServer: Boolean = false,
) {
    companion object {
        fun local(): PlaylistSource = PlaylistSource(
            url = PlaylistConfig.PLAYLIST_URL,
            userAgent = PlaylistConfig.USER_AGENT,
            referer = null,
            fromServer = false,
        )
    }
}
