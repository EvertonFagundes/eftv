package com.eftv.android

import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.view.View
import android.view.inputmethod.EditorInfo
import androidx.activity.addCallback
import androidx.appcompat.app.AppCompatActivity
import androidx.core.widget.doAfterTextChanged
import androidx.lifecycle.lifecycleScope
import androidx.recyclerview.widget.GridLayoutManager
import com.eftv.android.data.CatalogStore
import com.eftv.android.data.ChannelKind
import com.eftv.android.data.ChannelMode
import com.eftv.android.data.FreeTv
import com.eftv.android.databinding.ActivityCategoriesBinding
import com.eftv.android.ui.CategoryGridAdapter
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import timber.log.Timber

/**
 * Escolha de categoria com busca e quantidade de itens.
 *
 * Antes isso era um menu suspenso com dezenas de grupos sem numero nem
 * pesquisa: com 2.261 canais o cliente nao sabia o que estava escolhendo. A
 * mesma tela serve para canais, filmes e series (o tipo vem por extra).
 */
class CategoriesActivity : AppCompatActivity() {

    private lateinit var binding: ActivityCategoriesBinding
    private lateinit var adapter: CategoryGridAdapter
    private lateinit var store: CatalogStore
    private var kind: ChannelKind = ChannelKind.LIVE

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityCategoriesBinding.inflate(layoutInflater)
        setContentView(binding.root)

        kind = intent.getStringExtra(EXTRA_KIND)
            ?.let { runCatching { ChannelKind.valueOf(it) }.getOrNull() }
            ?: ChannelKind.LIVE

        store = CatalogStore.get(this)
        adapter = CategoryGridAdapter(kind, ::finishWith)
        binding.categoryList.layoutManager = GridLayoutManager(this, columnsFor(this))
        binding.categoryList.adapter = adapter
        binding.categoryList.setHasFixedSize(false)

        binding.toolbar.title = getString(R.string.categories_title)
        binding.toolbar.subtitle = getString(kindTitle())
        binding.toolbar.setNavigationIcon(R.drawable.ic_arrow_back)
        binding.toolbar.setNavigationOnClickListener { finish() }
        onBackPressedDispatcher.addCallback(this) { finish() }

        binding.searchInput.doAfterTextChanged { text ->
            adapter.filter(text?.toString().orEmpty())
            updateEmptyState()
        }
        binding.searchInput.setOnEditorActionListener { view, actionId, _ ->
            if (actionId == EditorInfo.IME_ACTION_SEARCH) {
                view.clearFocus()
                true
            } else {
                false
            }
        }

        loadCategories()
    }

    override fun onResume() {
        super.onResume()
        TvScreen.apply(this)
    }

    private fun loadCategories() {
        val adultEnabled = SettingsActivity.isAdultContentEnabled(this)
        val selectedMode = intent.getStringExtra(EXTRA_MODE)
            ?.let { runCatching { ChannelMode.valueOf(it) }.getOrNull() }
            ?: ChannelMode.ALL
        val selectedGroup = intent.getStringExtra(EXTRA_GROUP)

        lifecycleScope.launch {
            val items = withContext(Dispatchers.IO) { buildItems(adultEnabled) }
            adapter.submit(items, selectedMode, selectedGroup)
            updateEmptyState()

            // Abre ja na categoria atual e, no controle remoto, foca um cartao.
            val current = adapter.positionOfSelected()
            if (current > 0) {
                (binding.categoryList.layoutManager as? GridLayoutManager)
                    ?.scrollToPositionWithOffset(current, 0)
            }
            binding.categoryList.post { binding.categoryList.requestFocus() }
        }
    }

    private fun buildItems(adultEnabled: Boolean): List<CategoryGridAdapter.Item> {
        val all = store.count(null, "", ChannelMode.ALL, kind)
        val favorites = store.count(null, "", ChannelMode.FAVORITES, kind)
        val recents = store.count(null, "", ChannelMode.RECENTS, kind)

        val items = ArrayList<CategoryGridAdapter.Item>()
        items.add(
            card(
                label = getString(R.string.categories_all),
                count = all,
                mode = ChannelMode.ALL,
                group = null,
                icon = R.drawable.ic_tv,
                accent = R.color.cat_all,
                container = R.color.cat_all_container,
            ),
        )
        if (favorites > 0) {
            items.add(
                card(
                    label = getString(R.string.favorites),
                    count = favorites,
                    mode = ChannelMode.FAVORITES,
                    group = null,
                    icon = R.drawable.ic_star,
                    accent = R.color.cat_religious,
                    container = R.color.cat_religious_container,
                ),
            )
        }
        if (recents > 0) {
            items.add(
                card(
                    label = getString(R.string.recents),
                    count = recents,
                    mode = ChannelMode.RECENTS,
                    group = null,
                    icon = R.drawable.ic_history,
                    accent = R.color.cat_news,
                    container = R.color.cat_news_container,
                ),
            )
        }

        // TV aberta: reunida pelo nome do canal (Globo, Record, SBT...), mesmo
        // que o provedor espalhe esses canais em grupos diferentes.
        if (kind == ChannelKind.LIVE) {
            val openTv = store.count(FreeTv.GROUP, "", ChannelMode.ALL, kind)
            if (openTv > 0) {
                items.add(
                    card(
                        label = getString(R.string.category_open_tv),
                        count = openTv,
                        mode = ChannelMode.ALL,
                        group = FreeTv.GROUP,
                        icon = R.drawable.ic_live_tv,
                        accent = R.color.cat_abertos,
                        container = R.color.cat_abertos_container,
                    ),
                )
            }
        }

        for (group in store.groupsWithCounts(kind)) {
            if (group.title.isBlank()) continue
            if (!adultEnabled && ChannelKind.isAdultGroup(group.title)) continue
            // "Abertos" da playlist ja esta coberto pela categoria virtual.
            if (kind == ChannelKind.LIVE && group.title.normalizedForLabel().contains("aberto")) continue
            val style = styleFor(group.title)
            val label = cleanLabel(group.title)
            items.add(
                card(
                    label = label,
                    count = group.count,
                    mode = ChannelMode.ALL,
                    group = group.title,
                    icon = style.icon,
                    accent = style.accent,
                    container = style.container,
                ),
            )
        }

        Timber.d("Categorias de %s: %d itens", kind, items.size)
        return items
    }

    private fun card(
        label: String,
        count: Int,
        mode: ChannelMode,
        group: String?,
        icon: Int,
        accent: Int,
        container: Int,
    ) = CategoryGridAdapter.Item(
        selection = CategoryGridAdapter.Selection(label = label, mode = mode, group = group),
        count = count,
        iconRes = icon,
        accentRes = accent,
        containerRes = container,
    )

    /** Icone e cor por assunto do grupo (o provedor muda os nomes com frequencia). */
    private data class Style(val icon: Int, val accent: Int, val container: Int)

    /**
     * Tira o prefixo repetido do provedor ("Canais | ") do texto exibido.
     * O filtro continua usando o nome completo do grupo.
     */
    private fun cleanLabel(title: String): String {
        val cleaned = title
            .replace(Regex("(?i)^\\s*canais\\s*[|\\-–:]\\s*"), "")
            .trim()
        if (cleaned.isBlank()) return title
        return cleaned.replaceFirstChar { it.uppercase() }
    }

    /** Texto sem acento e em minusculas, para comparar nomes de grupo. */
    private fun String.normalizedForLabel(): String = lowercase()
        .replace(Regex("[áàâãä]"), "a")
        .replace(Regex("[éèêë]"), "e")
        .replace(Regex("[íìîï]"), "i")
        .replace(Regex("[óòôõö]"), "o")
        .replace(Regex("[úùûü]"), "u")
        .replace("ç", "c")

    private fun styleFor(title: String): Style {
        val key = title.lowercase()
        fun has(vararg words: String) = words.any { key.contains(it) }

        return when {
            has("filme", "cinema") -> Style(R.drawable.ic_movie, R.color.cat_movie, R.color.cat_movie_container)
            has("serie", "série", "novela") ->
                Style(R.drawable.ic_series, R.color.cat_series, R.color.cat_series_container)
            has("infantil", "crianc", "kids", "desenho") ->
                Style(R.drawable.ic_child_friendly, R.color.cat_child, R.color.cat_child_container)
            has("esporte", "jogo", "futebol", "luta") ->
                Style(R.drawable.ic_sports, R.color.cat_sports, R.color.cat_sports_container)
            has("noticia", "notícia", "jornal", "news") ->
                Style(R.drawable.ic_news, R.color.cat_news, R.color.cat_news_container)
            has("aberto", "aberta") -> Style(R.drawable.ic_live_tv, R.color.cat_abertos, R.color.cat_abertos_container)
            has("document") ->
                Style(R.drawable.ic_documentary, R.color.cat_documentary, R.color.cat_documentary_container)
            // Emissoras: o provedor agrupa por praça ("Globos Sudeste"), mas para
            // o cliente e TV aberta. Fica depois de "noticia/news" para nao
            // capturar GloboNews, Record News e Band News.
            has("globo", "record", "sbt", "band", "redetv", "rede tv", "cultura", "tv brasil", "gazeta", "aparecida") ->
                Style(R.drawable.ic_live_tv, R.color.cat_abertos, R.color.cat_abertos_container)
            has("anime") -> Style(R.drawable.ic_anime, R.color.cat_anime, R.color.cat_anime_container)
            has("religio", "religi", "deus") ->
                Style(R.drawable.ic_religious, R.color.cat_religious, R.color.cat_religious_container)
            has("musica", "música", "clipe") -> Style(R.drawable.ic_music, R.color.cat_music, R.color.cat_music_container)
            has("24") -> Style(R.drawable.ic_24h, R.color.cat_24h, R.color.cat_24h_container)
            has("stream", "flix", "prime", "hbo", "globoplay") ->
                Style(R.drawable.ic_streaming, R.color.cat_streaming, R.color.cat_streaming_container)
            has("adult", "xxx", "+18") -> Style(R.drawable.ic_adults, R.color.cat_adults, R.color.cat_adults_container)
            has("varied") -> Style(R.drawable.ic_variety, R.color.cat_variety, R.color.cat_variety_container)
            else -> Style(R.drawable.ic_other, R.color.cat_other, R.color.cat_other_container)
        }
    }

    private fun kindTitle(): Int = when (kind) {
        ChannelKind.MOVIE -> R.string.category_kind_movies
        ChannelKind.SERIES -> R.string.category_kind_series
        else -> R.string.category_kind_channels
    }

    private fun updateEmptyState() {
        val empty = adapter.itemCount == 0
        binding.emptyText.visibility = if (empty) View.VISIBLE else View.GONE
        binding.categoryList.visibility = if (empty) View.GONE else View.VISIBLE
    }

    private fun finishWith(selection: CategoryGridAdapter.Selection) {
        val data = Intent()
            .putExtra(RESULT_LABEL, selection.label)
            .putExtra(RESULT_MODE, selection.mode.name)
            .putExtra(RESULT_GROUP, selection.group)
        setResult(RESULT_OK, data)
        finish()
    }

    companion object {
        const val EXTRA_KIND = "extra_kind"
        const val EXTRA_MODE = "extra_mode"
        const val EXTRA_GROUP = "extra_group"

        const val RESULT_LABEL = "result_label"
        const val RESULT_MODE = "result_mode"
        const val RESULT_GROUP = "result_group"

        /** Duas colunas no celular, mais no tablet/TV (texto grande a distancia). */
        fun columnsFor(context: Context): Int {
            val widthDp = context.resources.configuration.screenWidthDp
            return when {
                widthDp >= 960 -> 4
                widthDp >= 600 -> 3
                else -> 2
            }
        }
    }
}
