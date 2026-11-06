package com.eftv.android

import android.content.Intent
import android.os.Bundle
import androidx.appcompat.app.AppCompatActivity
import androidx.core.view.isVisible
import androidx.lifecycle.lifecycleScope
import androidx.recyclerview.widget.LinearLayoutManager
import coil.load
import com.eftv.android.data.CatalogStore
import com.eftv.android.data.Channel
import com.eftv.android.databinding.ActivitySeriesBinding
import com.eftv.android.ui.EpisodeAdapter
import com.google.android.material.tabs.TabLayout
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import timber.log.Timber

/**
 * Detalhe de uma serie: capa, abas de temporada e a lista de episodios.
 * Tocar num episodio abre o player.
 */
class SeriesActivity : AppCompatActivity() {

    private lateinit var binding: ActivitySeriesBinding
    private val catalog by lazy { CatalogStore.get(this) }

    private val adapter = EpisodeAdapter(::playEpisode)
    private var seasons: List<Int> = emptyList()
    private var episodesBySeason: Map<Int, List<Channel>> = emptyMap()

    private var seriesKey = ""
    private var seriesTitle = ""
    private var seriesLogo = ""
    private var userAgent: String? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivitySeriesBinding.inflate(layoutInflater)
        setContentView(binding.root)

        seriesKey = intent.getStringExtra(EXTRA_KEY).orEmpty()
        seriesTitle = intent.getStringExtra(EXTRA_TITLE).orEmpty()
        seriesLogo = intent.getStringExtra(EXTRA_LOGO).orEmpty()
        userAgent = intent.getStringExtra(EXTRA_USER_AGENT)

        setSupportActionBar(binding.toolbar)
        supportActionBar?.title = seriesTitle
        binding.toolbar.setNavigationIcon(R.drawable.ic_arrow_back)
        binding.toolbar.setNavigationOnClickListener { finish() }

        binding.seriesTitle.text = seriesTitle
        binding.seriesPoster.load(seriesLogo.ifBlank { null }) {
            placeholder(R.drawable.ic_series)
            error(R.drawable.ic_series)
            fallback(R.drawable.ic_series)
            crossfade(true)
        }

        binding.episodeList.layoutManager = LinearLayoutManager(this)
        binding.episodeList.adapter = adapter

        binding.seasonTabs.addOnTabSelectedListener(object : TabLayout.OnTabSelectedListener {
            override fun onTabSelected(tab: TabLayout.Tab) {
                showSeason(tab.position)
            }

            override fun onTabUnselected(tab: TabLayout.Tab) = Unit
            override fun onTabReselected(tab: TabLayout.Tab) = Unit
        })

        loadEpisodes()
    }

    override fun onResume() {
        super.onResume()
        // Ao voltar do player, atualiza "min restantes" dos episodios.
        val urls = episodesBySeason.values.flatten().map { it.url }
        if (urls.isEmpty()) return
        lifecycleScope.launch {
            val progress = withContext(Dispatchers.IO) { catalog.progressFor(urls) }
            adapter.updateProgress(progress)
        }
    }

    private fun loadEpisodes() {
        binding.loading.isVisible = true
        lifecycleScope.launch {
            val episodes = try {
                withContext(Dispatchers.IO) { catalog.episodes(seriesKey) }
            } catch (e: Exception) {
                Timber.e(e, "Falha ao carregar episodios de %s", seriesKey)
                emptyList()
            }
            binding.loading.isVisible = false

            // Mesma temporada/episodio repetido pelo provedor: fica o primeiro.
            val unique = episodes.distinctBy { it.season to it.episode }
            episodesBySeason = unique.groupBy { it.season }.toSortedMap()
            seasons = episodesBySeason.keys.toList()

            if (unique.isEmpty()) {
                binding.emptyText.isVisible = true
                binding.seasonTabs.isVisible = false
                return@launch
            }

            binding.seriesSummary.text = buildSummary(seasons.size, unique.size)
            binding.seasonTabs.removeAllTabs()
            seasons.forEach { season ->
                binding.seasonTabs.addTab(
                    binding.seasonTabs.newTab().setText(seasonLabel(season)),
                )
            }
            // Com uma unica temporada as abas nao ajudam.
            binding.seasonTabs.isVisible = seasons.size > 1
            showSeason(0)
        }
    }

    private fun showSeason(index: Int) {
        val season = seasons.getOrNull(index) ?: return
        adapter.submit(episodesBySeason[season].orEmpty())
        binding.episodeList.scrollToPosition(0)
    }

    private fun seasonLabel(season: Int): String =
        if (season == 0) {
            getString(R.string.series_season_specials)
        } else {
            getString(R.string.series_season_tab, season)
        }

    private fun buildSummary(seasonCount: Int, episodeCount: Int): String {
        val seasonsText =
            resources.getQuantityString(R.plurals.series_seasons_count, seasonCount, seasonCount)
        val episodesText =
            resources.getQuantityString(R.plurals.series_episodes_count, episodeCount, episodeCount)
        return "$seasonsText · $episodesText"
    }

    private fun playEpisode(episode: Channel) {
        lifecycleScope.launch(Dispatchers.IO) {
            catalog.markRecent(episode.url)
        }
        startActivity(
            Intent(this, PlayerActivity::class.java).apply {
                putExtra(PlayerActivity.EXTRA_URL, episode.url)
                putExtra(PlayerActivity.EXTRA_NAME, episode.name)
                putExtra(PlayerActivity.EXTRA_LOGO, episode.logo.ifBlank { seriesLogo })
                putExtra(PlayerActivity.EXTRA_USER_AGENT, episode.userAgent ?: userAgent)
                putExtra(PlayerActivity.EXTRA_REFERER, episode.referer)
                putExtra(PlayerActivity.EXTRA_KIND, episode.kind.name)
            }
        )
    }

    companion object {
        const val EXTRA_KEY = "extra_series_key"
        const val EXTRA_TITLE = "extra_series_title"
        const val EXTRA_LOGO = "extra_series_logo"
        const val EXTRA_USER_AGENT = "extra_series_user_agent"
    }
}
