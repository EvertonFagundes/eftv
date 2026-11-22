package com.eftv.android.ui

import android.widget.ImageView
import coil.load
import coil.request.ImageRequest
import com.eftv.android.data.Channel
import com.eftv.android.data.LocalServer

/**
 * Carrega a arte do catalogo com os mesmos headers da playlist/streams.
 *
 * Varios provedores servem as imagens atras de hotlink protection: sem o
 * User-Agent/Referer do painel a resposta e 403 e o card fica no placeholder.
 * Pior: ao rolar a lista, o Coil mantem a capa do item anterior ate a nova
 * imagem chegar, e o resultado parece "capa trocada". O padrao do Coil envia
 * apenas `Coil/<versao>`, que muitos CDNs bloqueiam.
 *
 * A imagem passa pelo servidor local (quando ele ja respondeu): assim herda o
 * DNS-over-HTTPS que resolve o host nos dados moveis e evita o cache de uma
 * URL direta que falhou na rede anterior.
 */
fun ImageView.loadChannelArt(channel: Channel, fallbackRes: Int) {
    val logo = channel.logo.trim()
    if (logo.isBlank()) {
        setImageResource(fallbackRes)
        return
    }
    val data = LocalServer.proxiedArtwork(logo)
    val request = ImageRequest.Builder(context)
        .data(data)
        .placeholder(fallbackRes)
        .error(fallbackRes)
        .fallback(fallbackRes)
        .crossfade(150)
        .apply {
            channel.userAgent
                ?.takeIf { it.isNotBlank() }
                ?.let { addHeader("User-Agent", it) }
            channel.referer
                ?.takeIf { it.isNotBlank() }
                ?.let { addHeader("Referer", it) }
        }
        .build()
    load(request)
}
