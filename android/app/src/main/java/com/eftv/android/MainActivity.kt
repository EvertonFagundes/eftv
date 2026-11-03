package com.eftv.android

import android.content.Intent
import android.os.Bundle
import android.view.View
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.core.widget.doAfterTextChanged
import androidx.lifecycle.lifecycleScope
import androidx.recyclerview.widget.LinearLayoutManager
import com.eftv.android.data.Channel
import com.eftv.android.data.PlaylistRepository
import com.eftv.android.data.PlaylistSource
import com.eftv.android.data.SessionStore
import com.eftv.android.data.api.EftvApi
import com.eftv.android.data.normalizedForSearch
import com.eftv.android.databinding.ActivityMainBinding
import com.eftv.android.ui.CategoryAdapter
import com.eftv.android.ui.ChannelAdapter
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
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
    private val channelAdapter = ChannelAdapter(::openPlayer)
    private val categoryAdapter = CategoryAdapter(::onCategorySelected)

    private var channels: List<Channel> = emptyList()
    private var selectedGroup: String = CategoryAdapter.ALL
    private var searchQuery: String = ""

    private var refreshJob: Job? = null
    private var filterJob: Job? = null

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
                applyCatalog(cached.channels, cached.updatedAt)
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
        if (refreshJob?.isActive == true) return

        val hasContent = channels.isNotEmpty()
        if (!hasContent) showLoading()
        binding.swipeRefresh.isRefreshing = hasContent

        refreshJob = lifecycleScope.launch {
            try {
                val result = repository.refresh()
                applyCatalog(result.channels, result.updatedAt)

                if (result.error != null) {
                    Toast.makeText(
                        this@MainActivity,
                        R.string.using_cached_list,
                        Toast.LENGTH_LONG,
                    ).show()
                }
                if (result.truncated) {
                    Toast.makeText(
                        this@MainActivity,
                        R.string.list_truncated,
                        Toast.LENGTH_LONG,
                    ).show()
                }
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

    private fun applyCatalog(list: List<Channel>, updatedAt: Long) {
        channels = list

        val groups = LinkedHashSet<String>()
        list.forEach { groups.add(it.group) }
        categoryAdapter.submit(groups.toList())

        selectedGroup = CategoryAdapter.ALL
        filterChannels(debounce = 0)

        binding.toolbar.subtitle = buildSubtitle(list.size, updatedAt)
        binding.swipeRefresh.visibility = View.VISIBLE
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
        filterJob?.cancel()

        val group = selectedGroup
        val query = searchQuery.normalizedForSearch()

        filterJob = lifecycleScope.launch {
            if (debounce > 0) delay(debounce)

            val source = channels
            val filtered = withContext(Dispatchers.Default) {
                if (group == CategoryAdapter.ALL && query.isEmpty()) {
                    source
                } else {
                    source.filter { channel ->
                        (group == CategoryAdapter.ALL || channel.group == group) &&
                            (query.isEmpty() || channel.searchKey.contains(query))
                    }
                }
            }

            channelAdapter.submit(filtered)

            when {
                filtered.isNotEmpty() -> binding.stateContainer.visibility = View.GONE
                source.isEmpty() -> showMessage(
                    getString(R.string.empty_catalog),
                    showProgress = false,
                    showRetry = false,
                )
                else -> showMessage(
                    getString(R.string.empty_search),
                    showProgress = false,
                    showRetry = false,
                )
            }
        }
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
