package com.eftv.android.ui

import android.widget.ImageView
import coil.load
import coil.request.ImageRequest
import com.eftv.android.PlaylistConfig
import com.eftv.android.data.Channel
import com.eftv.android.data.LocalServer
import com.eftv.android.data.NetworkInfo

/**
 * Carrega a arte do catalogo com os mesmos headers da playlist/streams.
 *
 * Varios provedores servem as imagens atras de hotlink protection: sem o
 * User-Agent/Referer do painel a resposta e 403 e o card fica no placeholder.
 * Pior: ao rolar a lista, o Coil mantem a capa do item anterior ate a nova
 * imagem chegar, e o resultado parece "capa trocada". O padrao do Coil envia
 * apenas `Coil/<versao>`, que muitos CDNs bloqueiam.
 *
 * A ordem depende da rede:
 *  - Wi-Fi: tenta a URL direta (caminho que ja funcionava) e, se falhar,
 *    tenta o proxy local;
 *  - dados moveis: tenta o proxy local (DNS-over-HTTPS) primeiro e cai para
 *    a URL direta.
 *
 * Quando todas as tentativas falham, entra a capa gerada com as iniciais do
 * canal: muitas listas antigas apontam para `goo.gl`/`postimg`, que sairam do
 * ar, e sem isso a tela inteira fica com o mesmo icone generico.
 */
fun ImageView.loadChannelArt(channel: Channel, fallbackRes: Int) {
    val logo = channel.logo.trim()
    if (logo.isBlank()) {
        setImageDrawable(CoverPlaceholder.drawable(context, channel.name, channel.kind, fallbackRes))
        return
    }

    val proxyUrl = LocalServer.artworkProxyUrl(logo)
    val useProxyFirst =
        proxyUrl != logo &&
            LocalServer.isServerReady() &&
            NetworkInfo.label(context) == "movel"

    val first = if (useProxyFirst) proxyUrl else logo
    val second = if (first == logo) proxyUrl else logo
    loadArtwork(first, second, channel, fallbackRes)
}

private fun ImageView.loadArtwork(
    data: String,
    fallbackData: String?,
    channel: Channel,
    fallbackRes: Int,
) {
    val userAgent = channel.userAgent
        ?.takeIf { it.isNotBlank() }
        ?: PlaylistConfig.USER_AGENT

    val request = ImageRequest.Builder(context)
        .data(data)
        .placeholder(CoverPlaceholder.drawable(context, channel.name, channel.kind, fallbackRes))
        .error(CoverPlaceholder.drawable(context, channel.name, channel.kind, fallbackRes))
        .fallback(CoverPlaceholder.drawable(context, channel.name, channel.kind, fallbackRes))
        .crossfade(150)
        .apply {
            if (userAgent.isNotBlank()) addHeader("User-Agent", userAgent)
            channel.referer
                ?.takeIf { it.isNotBlank() }
                ?.let { addHeader("Referer", it) }
        }
        .listener(
            onError = { _, _ ->
                if (!fallbackData.isNullOrBlank() && fallbackData != data) {
                    loadArtwork(fallbackData, null, channel, fallbackRes)
                }
            },
        )
        .build()
    load(request)
}
