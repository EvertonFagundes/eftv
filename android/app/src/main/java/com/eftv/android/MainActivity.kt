package com.eftv.android

import android.content.Intent
import android.os.Bundle
import android.view.View
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.core.widget.doAfterTextChanged
import androidx.lifecycle.lifecycleScope
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import com.eftv.android.data.Channel
import com.eftv.android.data.PlaylistRepository
import com.eftv.android.data.PlaylistSource
import com.eftv.android.data.SessionStore
import com.eftv.android.data.api.EftvApi
import com.eftv.android.data.normalizedForSearch
import com.eftv.android.databinding.ActivityMainBinding
import com.eftv.android.ui.CategoryAdapter
import com.eftv.android.ui.ChannelAdapter
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import timber.log.Timber
import java.text.DateFormat
import java.text.NumberFormat
import java.util.Date

class MainActivity : AppCompatActivity() {

    private lateinit var binding: ActivityMainBinding
    private val session by lazy { SessionStore(this) }
    private val api by lazy { EftvApi() }
    private lateinit var repository: PlaylistRepository
    private var source: PlaylistSource = PlaylistSource.local()
    private val channelAdapter = ChannelAdapter(::openPlayer, ::requestPage)
    private val categoryAdapter = CategoryAdapter(::onCategorySelected)

    private var selectedGroup: String = CategoryAdapter.ALL
    private var searchQuery: String = ""
    private var hasCatalog = false

    private var refreshJob: Job? = null
    private var filterJob: Job? = null
    private val pageJobs = HashMap<Int, Job>()
    private val loadingPages = HashSet<Int>()
    private var queryGeneration = 0

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)

        setupToolbar()
        setupLists()
        setupSearch()
        setupRefresh()

        startCatalog()
    }

    override fun onDestroy() {
        super.onDestroy()
        if (::repository.isInitialized) repository.close()
    }

    private fun setupToolbar() {
        binding.toolbar.inflateMenu(R.menu.menu_main)
        binding.toolbar.setOnMenuItemClickListener { item ->
            when (item.itemId) {
                R.id.action_refresh -> {
                    refreshCatalog()
                    true
                }

                R.id.action_logout -> {
                    logout()
                    true
                }

                else -> false
            }
        }
    }

    private fun setupLists() {
        binding.channelList.apply {
            layoutManager = LinearLayoutManager(this@MainActivity)
            adapter = channelAdapter
            setHasFixedSize(true)
            addOnScrollListener(object : RecyclerView.OnScrollListener() {
                override fun onScrolled(recyclerView: RecyclerView, dx: Int, dy: Int) {
                    if (!::repository.isInitialized) return
                    val manager = recyclerView.layoutManager as? LinearLayoutManager ?: return
                    val first = manager.findFirstVisibleItemPosition()
                    if (first == RecyclerView.NO_POSITION) return

                    val page = first / ChannelAdapter.PAGE_SIZE
                    channelAdapter.trim(page)
                    requestPage(page)
                    requestPage(page + 1)
                    if (dy < 0) requestPage(page - 1)
                }
            })
        }
        binding.categoryList.apply {
            layoutManager = LinearLayoutManager(
                this@MainActivity,
                LinearLayoutManager.HORIZONTAL,
                false,
            )
            adapter = categoryAdapter
            setHasFixedSize(true)
        }
    }

    private fun setupSearch() {
        binding.searchInput.doAfterTextChanged { text ->
            searchQuery = text?.toString().orEmpty()
            filterChannels(debounce = 250)
        }
    }

    private fun setupRefresh() {
        binding.swipeRefresh.setOnRefreshListener { refreshCatalog() }
        binding.retryButton.setOnClickListener { refreshCatalog() }
    }

    // ------------------------------------------------------------------
    // Catalogo
    // ------------------------------------------------------------------

    /**
     * Resolve a origem do catalogo: servidor (assinante autorizado) ou lista
     * local. Nunca bloqueia o app por causa do backend.
     */
    private fun startCatalog() {
        val skipAuth = intent.getBooleanExtra(EXTRA_SKIP_AUTH, false)

        lifecycleScope.launch {
            showLoading()
            source = if (skipAuth) PlaylistSource.local() else resolveSource()
            repository = PlaylistRepository(this@MainActivity, source)
            loadCatalog()
        }
    }

    private suspend fun resolveSource(): PlaylistSource {
        val token = session.accessToken()
        if (token.isNullOrBlank()) return PlaylistSource.local()

        return try {
            api.playlist(token).toSource()
        } catch (e: EftvApi.ApiException) {
            when (e.statusCode) {
                401 -> {
                    if (tryRefresh()) {
                        runCatching { api.playlist(session.accessToken().orEmpty()) }
                            .getOrNull()?.toSource()
                            ?: PlaylistSource.local()
                    } else {
                        session.clear()
                        goToLogin()
                        PlaylistSource.local()
                    }
                }

                403 -> {
                    Toast.makeText(
                        this@MainActivity,
                        R.string.subscription_inactive,
                        Toast.LENGTH_LONG,
                    ).show()
                    PlaylistSource.local()
                }

                503 -> {
                    Timber.w("Servidor sem playlist configurada; usando lista local")
                    PlaylistSource.local()
                }

                else -> PlaylistSource.local()
            }
        } catch (e: Exception) {
            Timber.w(e, "Backend indisponivel; usando lista local")
            PlaylistSource.local()
        }
    }

    private suspend fun tryRefresh(): Boolean {
        val refreshToken = session.refreshToken()
        if (refreshToken.isNullOrBlank()) return false

        return try {
            val tokens = api.refresh(refreshToken)
            session.save(tokens, session.email().orEmpty())
            true
        } catch (e: Exception) {
            Timber.w(e, "Nao foi possivel renovar a sessao")
            false
        }
    }

    private fun EftvApi.PlaylistAccess.toSource(): PlaylistSource = PlaylistSource(
        url = playlistUrl,
        userAgent = userAgent,
        referer = referer,
        fromServer = true,
    )

    private fun goToLogin() {
        startActivity(
            Intent(this, LoginActivity::class.java).apply {
                addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP)
            }
        )
        finish()
    }

    private fun logout() {
        session.clear()
        goToLogin()
    }

    private fun loadCatalog() {
        lifecycleScope.launch {
            showLoading()
            val cached = withContext(Dispatchers.IO) { repository.cached() }
            if (cached != null) {
                applyCatalog(cached)
                // Cache antigo: atualiza em segundo plano sem esconder a lista.
                if (System.currentTimeMillis() - cached.updatedAt > CACHE_TTL_MS) {
                    refreshCatalog()
                }
            } else {
                refreshCatalog()
            }
        }
    }

    private fun refreshCatalog() {
        if (!::repository.isInitialized) return
        if (refreshJob?.isActive == true) return

        val hasContent = hasCatalog
        if (!hasContent) showLoading()
        binding.swipeRefresh.isRefreshing = hasContent

        refreshJob = lifecycleScope.launch {
            try {
                val result = repository.refresh { count ->
                    runOnUiThread {
                        if (!hasContent && !isFinishing) {
                            binding.stateText.text = getString(
                                R.string.importing_channels,
                                NumberFormat.getIntegerInstance().format(count),
                            )
                        }
                    }
                }
                applyCatalog(result.metadata)

                if (result.error != null) {
                    Toast.makeText(
                        this@MainActivity,
                        R.string.using_cached_list,
                        Toast.LENGTH_LONG,
                    ).show()
                }
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                Timber.e(e, "Falha ao carregar o catalogo")
                if (hasContent) {
                    Toast.makeText(
                        this@MainActivity,
                        e.message ?: getString(R.string.load_error),
                        Toast.LENGTH_LONG,
                    ).show()
                } else {
                    showError(e.message)
                }
            } finally {
                binding.swipeRefresh.isRefreshing = false
            }
        }
    }

    private suspend fun applyCatalog(metadata: com.eftv.android.data.CatalogStore.Metadata) {
        hasCatalog = metadata.total > 0

        val groups = withContext(Dispatchers.IO) { repository.catalogStore.groups() }
        categoryAdapter.submit(groups)

        selectedGroup = CategoryAdapter.ALL
        binding.toolbar.subtitle = buildSubtitle(metadata.total, metadata.updatedAt)
        binding.swipeRefresh.visibility = View.VISIBLE
        filterChannels(debounce = 0)
    }

    private fun buildSubtitle(count: Int, updatedAt: Long): String {
        val quantity = NumberFormat.getIntegerInstance().format(count)
        val time = if (updatedAt > 0) {
            DateFormat.getTimeInstance(DateFormat.SHORT).format(Date(updatedAt))
        } else {
            "--:--"
        }
        val demo = if (source.url.isBlank()) " • demo" else if (source.fromServer) " • online" else ""
        return "$quantity canais • $time$demo"
    }

    private fun onCategorySelected(group: String) {
        selectedGroup = group
        filterChannels(debounce = 0)
    }

    private fun filterChannels(debounce: Long) {
        if (!::repository.isInitialized) return

        filterJob?.cancel()
        resetPaging()

        val group = selectedGroup.takeUnless { it == CategoryAdapter.ALL }
        val query = searchQuery.normalizedForSearch()

        filterJob = lifecycleScope.launch {
            if (debounce > 0) delay(debounce)

            val total = withContext(Dispatchers.IO) {
                repository.catalogStore.count(group, query)
            }
            if (!isActive) return@launch

            channelAdapter.reset(total)
            binding.channelList.scrollToPosition(0)

            if (total > 0) {
                binding.stateContainer.visibility = View.GONE
                requestPage(0)
                requestPage(1)
            } else {
                showMessage(
                    getString(if (hasCatalog) R.string.empty_search else R.string.empty_catalog),
                    showProgress = false,
                    showRetry = false,
                )
            }
        }
    }

    private fun requestPage(page: Int) {
        if (page < 0) return
        if (!::repository.isInitialized) return
        if (page * ChannelAdapter.PAGE_SIZE >= channelAdapter.itemCount) return
        if (channelAdapter.isPageLoaded(page)) return
        if (!loadingPages.add(page)) return

        val generation = queryGeneration
        val group = selectedGroup.takeUnless { it == CategoryAdapter.ALL }
        val query = searchQuery.normalizedForSearch()

        val job = lifecycleScope.launch {
            try {
                val items = withContext(Dispatchers.IO) {
                    repository.catalogStore.page(
                        group = group,
                        query = query,
                        limit = ChannelAdapter.PAGE_SIZE,
                        offset = page * ChannelAdapter.PAGE_SIZE,
                    )
                }
                if (generation == queryGeneration) {
                    channelAdapter.putPage(page, items)
                    channelAdapter.trim(page)
                }
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                Timber.e(e, "Falha ao carregar pagina %d do catalogo", page)
            } finally {
                if (generation == queryGeneration) {
                    loadingPages.remove(page)
                    pageJobs.remove(page)
                }
            }
        }
        pageJobs[page] = job
    }

    private fun resetPaging() {
        queryGeneration++
        pageJobs.values.forEach { it.cancel() }
        pageJobs.clear()
        loadingPages.clear()
    }

    private fun openPlayer(channel: Channel) {
        startActivity(
            Intent(this, PlayerActivity::class.java).apply {
                putExtra(PlayerActivity.EXTRA_URL, channel.url)
                putExtra(PlayerActivity.EXTRA_NAME, channel.name)
                putExtra(PlayerActivity.EXTRA_LOGO, channel.logo)
                putExtra(
                    PlayerActivity.EXTRA_USER_AGENT,
                    channel.userAgent ?: source.userAgent,
                )
                putExtra(PlayerActivity.EXTRA_REFERER, channel.referer)
            }
        )
    }

    // ------------------------------------------------------------------
    // Estados da tela
    // ------------------------------------------------------------------

    private fun showLoading() {
        showMessage(getString(R.string.loading_channels), showProgress = true, showRetry = false)
    }

    private fun showError(message: String?) {
        showMessage(
            message ?: getString(R.string.load_error),
            showProgress = false,
            showRetry = true,
        )
    }

    private fun showMessage(message: String, showProgress: Boolean, showRetry: Boolean) {
        binding.stateContainer.visibility = View.VISIBLE
        binding.stateProgress.visibility = if (showProgress) View.VISIBLE else View.GONE
        binding.stateText.text = message
        binding.retryButton.visibility = if (showRetry) View.VISIBLE else View.GONE
    }

    companion object {
        const val EXTRA_SKIP_AUTH = "extra_skip_auth"

        /** Depois disso, o app tenta atualizar a lista em segundo plano. */
        private const val CACHE_TTL_MS = 6 * 60 * 60 * 1000L
    }
}
