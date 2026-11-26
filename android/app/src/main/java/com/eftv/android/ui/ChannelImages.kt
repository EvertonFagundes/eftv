package com.eftv.android.ui

import android.widget.ImageView
import androidx.lifecycle.findViewTreeLifecycleOwner
import androidx.lifecycle.lifecycleScope
import coil.load
import com.eftv.android.PlaylistConfig
import com.eftv.android.R
import com.eftv.android.data.Channel
import com.eftv.android.data.LocalServer
import com.eftv.android.data.NetworkInfo
import com.eftv.android.data.SeriesCoverFetcher
import kotlinx.coroutines.launch
import timber.log.Timber

/**
 * Carrega a arte do catalogo com os mesmos headers da playlist/streams.
 *
 * Varios provedores servem as imagens atras de hotlink protection: sem o
 * User-Agent/Referer do painel a resposta e 403 e o card fica no placeholder.
 * Pior: ao rolar a lista, o Coil mantem a capa do item anterior ate a nova
 * imagem chegar, e o resultado parece "capa trocada". O padrao do Coil envia
 * apenas `Coil/<versao>`, que muitos CDNs bloqueiam.
 *
 * A ordem depende da rede e do esquema da URL:
 *  - HTTPS no Wi-Fi: tenta a URL direta e, se falhar, o proxy local;
 *  - HTTP claro (ou qualquer URL nos dados moveis): tenta o proxy local
 *    primeiro, porque a conexao direta costuma ficar pendurada no provedor;
 *  - a segunda tentativa sempre usa o caminho oposto.
 *
 * Quando todas as tentativas falham, entra a capa gerada com as iniciais do
 * canal: muitas listas antigas apontam para `goo.gl`/`postimg`, que sairam do
 * ar, e sem isso a tela inteira fica com o mesmo icone generico.
 */
fun ImageView.loadChannelArt(channel: Channel, fallbackRes: Int) {
    val logo = channel.logo.trim()
    // A capa fica no fundo da ImageView. O Coil troca apenas o src; se o
    // download falhar, limpar o src ou carregar uma imagem transparente, a
    // capa continua aparecendo atras. Antes o card ficava vazio nesses casos.
    background = CoverPlaceholder.drawable(context, channel.name, channel.kind, fallbackRes)
    setImageDrawable(null)

    // Card de serie agrupada: quando o provedor traz uma capa propria, ela
    // vem primeiro (com o mesmo proxy/headers dos demais cards). So quando
    // nao ha capa, ou o download falha, buscamos uma capa real por titulo
    // (IMDb/TVMaze) e, por fim, mantemos a capa gerada.
    if (channel.isSeriesCard) {
        val view = this
        view.setTag(R.id.series_cover_key, channel.name)

        // A capa e apenas enfeite: se a busca falhar, mantemos a capa gerada
        // em vez de derrubar o app. Escopo da view evita trabalho orfao.
        val loadFetchedCover: () -> Unit = {
            view.findViewTreeLifecycleOwner()?.lifecycleScope?.launch {
                val url = try {
                    SeriesCoverFetcher.fetch(channel.name)
                } catch (e: kotlinx.coroutines.CancellationException) {
                    throw e
                } catch (e: Exception) {
                    Timber.w(e, "Falha ao buscar capa da serie")
                    null
                }
                if (view.getTag(R.id.series_cover_key) != channel.name) return@launch
                if (!url.isNullOrBlank()) {
                    val proxy = LocalServer.artworkProxyUrl(url)
                    val proxyFirst = proxy != url &&
                        LocalServer.isServerReady() &&
                        NetworkInfo.label(view.context) == "movel"
                    val first = if (proxyFirst) proxy else url
                    val second = if (first == url) proxy else url
                    // A capa externa nao pertence ao provedor: nao envia o
                    // Referer dele para o CDN do IMDb/TVMaze.
                    view.loadArtwork(
                        first,
                        second,
                        channel.copy(userAgent = null, referer = null),
                        fallbackRes,
                    )
                }
            }
            Unit
        }

        if (logo.isBlank()) {
            loadFetchedCover()
            return
        }

        val proxyUrl = LocalServer.artworkProxyUrl(logo)
        val useProxyFirst =
            proxyUrl != logo &&
                LocalServer.isServerReady() &&
                (NetworkInfo.label(context) == "movel" || logo.startsWith("http://"))
        val first = if (useProxyFirst) proxyUrl else logo
        val second = if (first == logo) proxyUrl else logo
        loadArtwork(first, second, channel, fallbackRes, onFinalError = loadFetchedCover)
        return
    }

    if (logo.isBlank()) {
        return
    }

    val proxyUrl = LocalServer.artworkProxyUrl(logo)
    // Em HTTP claro a conexao direta com varios provedores fica pendurada
    // (SYN aceito, resposta nunca chega) e o Coil espera ate o timeout. O
    // proxy local resolve por DNS-over-HTTPS e responde rapido, entao ele
    // vem primeiro. HTTPS continua direto no Wi-Fi.
    val useProxyFirst =
        proxyUrl != logo &&
            LocalServer.isServerReady() &&
            (NetworkInfo.label(context) == "movel" || logo.startsWith("http://"))

    val first = if (useProxyFirst) proxyUrl else logo
    val second = if (first == logo) proxyUrl else logo
    loadArtwork(first, second, channel, fallbackRes)
}

private fun ImageView.loadArtwork(
    data: String,
    fallbackData: String?,
    channel: Channel,
    fallbackRes: Int,
    onFinalError: (() -> Unit)? = null,
) {
    val userAgent = channel.userAgent
        ?.takeIf { it.isNotBlank() }
        ?: PlaylistConfig.USER_AGENT

    // Reforca o fundo ao trocar para a segunda URL (proxy/direta).
    background = CoverPlaceholder.drawable(context, channel.name, channel.kind, fallbackRes)
    setImageDrawable(null)

    // Coil 2.6: `ImageView.load(data) { ... }` cria o request com target na
    // propria ImageView. Passar um ImageRequest pronto aqui faria o Coil
    // trata-lo como *dado* (sem fetcher) e nada seria baixado.
    load(data) {
        if (userAgent.isNotBlank()) addHeader("User-Agent", userAgent)
        channel.referer
            ?.takeIf { it.isNotBlank() }
            ?.let { addHeader("Referer", it) }
        listener(
            onError = { _, _ ->
                if (!fallbackData.isNullOrBlank() && fallbackData != data) {
                    loadArtwork(fallbackData, null, channel, fallbackRes, onFinalError)
                } else {
                    background = CoverPlaceholder.drawable(
                        context,
                        channel.name,
                        channel.kind,
                        fallbackRes,
                    )
                    setImageDrawable(null)
                    onFinalError?.invoke()
                }
            },
        )
    }
}
