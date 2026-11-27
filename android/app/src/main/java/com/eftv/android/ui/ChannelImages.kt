package com.eftv.android.ui

import android.content.Context
import android.content.ContextWrapper
import android.widget.ImageView
import androidx.lifecycle.LifecycleOwner
import androidx.lifecycle.lifecycleScope
import coil.load
import com.eftv.android.PlaylistConfig
import com.eftv.android.R
import com.eftv.android.data.Channel
import com.eftv.android.data.ChannelKind
import com.eftv.android.data.LocalServer
import com.eftv.android.data.NetworkInfo
import com.eftv.android.data.SeriesCoverFetcher
import com.eftv.android.data.SeriesParser
import kotlinx.coroutines.CancellationException
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
 *
 * Series sao a excecao: o logo da playlist costuma apontar para uma imagem
 * aleatoria/trocada. A capa vem apenas da API publica (IMDb/TVMaze), buscada
 * pelo titulo da serie. Sem resultado, mantemos a capa gerada em vez de
 * mostrar a imagem errada do provedor. Canais e filmes nao mudam.
 */
fun ImageView.loadChannelArt(channel: Channel, fallbackRes: Int) {
    // Series: ignora o logo do provedor (ele e o responsavel pelas imagens
    // aleatorias) e busca a capa pelo titulo. Vale para cards agrupados, itens
    // soltos da aba Series e episodios em "Continuar assistindo".
    val seriesTitle = seriesCoverTitle(channel)
    if (seriesTitle != null) {
        loadSeriesCover(seriesTitle, fallbackRes)
        return
    }

    val logo = channel.logo.trim()
    // O RecyclerView reaproveita as views: sem trocar a chave, uma busca de
    // capa ainda em andamento podia terminar e pintar o item errado.
    setTag(R.id.series_cover_key, null)
    // A capa fica no fundo da ImageView. O Coil troca apenas o src; se o
    // download falhar, limpar o src ou carregar uma imagem transparente, a
    // capa continua aparecendo atras. Antes o card ficava vazio nesses casos.
    background = CoverPlaceholder.drawable(context, channel.name, channel.kind, fallbackRes)
    setImageDrawable(null)

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

/**
 * Titulo limpo para consultar a API de capas. Cards agrupados ja trazem o
 * titulo da serie; episodios soltos podem vir com "S01E02" no nome.
 */
private fun seriesCoverTitle(channel: Channel): String? {
    if (channel.kind != ChannelKind.SERIES) return null
    val title = channel.seriesTitle.takeIf { it.isNotBlank() }
        ?: SeriesParser.parse(channel.name)?.title
        ?: channel.name
    return title.trim().takeIf { it.isNotBlank() }
}

/**
 * Capa de serie buscada por titulo na API publica (IMDb/TVMaze).
 *
 * O logo da playlist e ignorado de proposito: ele aponta para imagens
 * aleatorias/trocadas. Enquanto a busca roda, o fundo gerado permanece; se
 * nao houver resultado, ele continua no lugar da imagem errada.
 */
internal fun ImageView.loadSeriesCover(title: String, fallbackRes: Int) {
    val view = this
    val query = title.trim()
    if (query.isBlank()) return

    // RecyclerView recicla views: a chave impede que uma busca antiga pinte
    // o card novo quando a resposta chegar.
    setTag(R.id.series_cover_key, query)
    background = CoverPlaceholder.drawable(context, query, ChannelKind.SERIES, fallbackRes)
    setImageDrawable(null)

    val startFetch = {
        // O item pode nao estar anexado no bind; subimos pelo ContextWrapper
        // ate a Activity para ter um escopo que acompanhe o ciclo de vida.
        val owner = view.context.findLifecycleOwner()
        owner?.lifecycleScope?.launch {
            if (view.getTag(R.id.series_cover_key) != query) return@launch
            val url = try {
                SeriesCoverFetcher.fetch(query)
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                Timber.w(e, "Falha ao buscar capa da serie")
                null
            }
            if (view.getTag(R.id.series_cover_key) != query) return@launch
            if (url.isNullOrBlank()) return@launch

            val proxy = LocalServer.artworkProxyUrl(url)
            val proxyFirst = proxy != url &&
                LocalServer.isServerReady() &&
                NetworkInfo.label(view.context) == "movel"
            val first = if (proxyFirst) proxy else url
            val second = if (first == url) proxy else url
            // A CDN da API nao e a do provedor: nao envia o Referer dele.
            view.loadArtwork(
                first,
                second,
                Channel(
                    name = query,
                    group = "",
                    logo = url,
                    url = "",
                    kind = ChannelKind.SERIES,
                ),
                fallbackRes,
            )
        }
        Unit
    }
    if (view.isAttachedToWindow) startFetch() else view.post { startFetch() }
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

/**
 * Activity dona do contexto, mesmo quando ele vem embrulhado em um
 * ContextThemeWrapper (caso comum dos itens do RecyclerView).
 */
private tailrec fun Context.findLifecycleOwner(): LifecycleOwner? = when (this) {
    is LifecycleOwner -> this
    is ContextWrapper -> baseContext.findLifecycleOwner()
    else -> null
}
