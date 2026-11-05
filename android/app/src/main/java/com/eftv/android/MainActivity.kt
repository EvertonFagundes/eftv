package com.eftv.android

import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Bundle
import android.text.SpannableString
import android.text.style.ForegroundColorSpan
import android.view.View
import android.view.WindowManager
import android.view.inputmethod.EditorInfo
import android.view.inputmethod.InputMethodManager
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.core.widget.doAfterTextChanged
import androidx.lifecycle.lifecycleScope
import androidx.recyclerview.widget.GridLayoutManager
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import com.eftv.android.data.CatalogStore
import com.eftv.android.data.Channel
import com.eftv.android.data.ChannelMode
import com.eftv.android.data.DeviceIdentity
import com.eftv.android.data.PlaylistRepository
import com.eftv.android.data.PlaylistSource
import com.eftv.android.data.SessionStore
import com.eftv.android.data.api.EftvApi
import com.eftv.android.data.normalizedForSearch
import com.eftv.android.databinding.ActivityMainBinding
import com.eftv.android.ui.CategoryAdapter
import com.eftv.android.ui.ChannelAdapter
import com.google.android.material.dialog.MaterialAlertDialogBuilder
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
    private val device by lazy { DeviceIdentity(this) }
    private val api by lazy {
        EftvApi(deviceId = device.id, deviceName = device.name)
    }
    private lateinit var repository: PlaylistRepository
    private var source: PlaylistSource = PlaylistSource.local()
    private val channelAdapter = ChannelAdapter(::openPlayer, ::requestPage, ::toggleFavorite)
    private val categoryAdapter = CategoryAdapter(::onCategorySelected)

    private var selectedCategory = CategoryAdapter.Category(CategoryAdapter.ALL)
    private var selectedMode = ChannelMode.ALL
    private var selectedGroup: String? = null
    private var catalogMetadata: CatalogStore.Metadata? = null

    /** Aparelho barrado pelo servidor: nao mostra nem usa o catalogo local. */
    private var deviceBlocked = false
    private var searchQuery: String = ""
    private var hasCatalog = false

    private var refreshJob: Job? = null
    private var filterJob: Job? = null
    private val pageJobs = HashMap<Int, Job>()
    private val loadingPages = HashSet<Int>()
    private var queryGeneration = 0

    private val isTelevision: Boolean by lazy {
        packageManager.hasSystemFeature(PackageManager.FEATURE_LEANBACK) ||
            packageManager.hasSystemFeature(PackageManager.FEATURE_TELEVISION)
    }

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
                    refreshCatalog(revalidateSource = true)
                    true
                }

                R.id.action_device -> {
                    showDeviceDialog()
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
        val columns = resources.getInteger(R.integer.channel_columns).coerceAtLeast(1)
        binding.channelList.apply {
            layoutManager = if (columns > 1) {
                GridLayoutManager(this@MainActivity, columns)
            } else {
                LinearLayoutManager(this@MainActivity)
            }
            adapter = channelAdapter
            setHasFixedSize(true)
            addOnScrollListener(object : RecyclerView.OnScrollListener() {
                override fun onScrolled(recyclerView: RecyclerView, dx: Int, dy: Int) {
                    if (dy != 0) hideKeyboard()
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
        binding.searchInput.setOnEditorActionListener { _, actionId, _ ->
            if (actionId == EditorInfo.IME_ACTION_SEARCH || actionId == EditorInfo.IME_ACTION_DONE) {
                hideKeyboard()
                true
            } else {
                false
            }
        }
        // Na TV o teclado deve abrir apenas quando o usuario escolher a busca.
        if (isTelevision) {
            window.setSoftInputMode(WindowManager.LayoutParams.SOFT_INPUT_STATE_ALWAYS_HIDDEN)
            binding.searchInput.clearFocus()
        }
    }

    private fun setupRefresh() {
        binding.swipeRefresh.setOnRefreshListener { refreshCatalog(revalidateSource = true) }
        binding.retryButton.setOnClickListener { refreshCatalog(revalidateSource = true) }
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
            source = if (skipAuth) {
                PlaylistSource.local()
            } else {
                try {
                    resolveSource()
                } catch (e: DeviceBlockedException) {
                    showDeviceBlocked(e.message.orEmpty())
                    return@launch
                }
            }
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
                        try {
                            api.playlist(session.accessToken().orEmpty()).toSource()
                        } catch (retry: EftvApi.ApiException) {
                            // Renovou a sessao, mas o aparelho continua barrado.
                            if (retry.isDeviceBlock()) throw DeviceBlockedException(retry.detail)
                            Toast.makeText(
                                this@MainActivity,
                                R.string.subscription_inactive,
                                Toast.LENGTH_LONG,
                            ).show()
                            PlaylistSource.local()
                        }
                    } else {
                        session.clear()
                        goToLogin()
                        PlaylistSource.local()
                    }
                }

                403 -> {
                    if (e.isDeviceBlock()) {
                        // Nao cai para a lista local: o aparelho nao esta autorizado.
                        throw DeviceBlockedException(e.detail)
                    }
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

    /**
     * Revalida o acesso ao servidor ao atualizar manualmente.
     *
     * Diferente da abertura do app, uma falha de rede aqui mantem a origem
     * atual (nao troca a playlist por uma lista local). Bloqueio de aparelho e
     * assinatura inativa sao aplicados na hora.
     */
    private suspend fun revalidateServerAccess() {
        val token = session.accessToken() ?: return

        try {
            source = api.playlist(token).toSource()
        } catch (e: EftvApi.ApiException) {
            when {
                e.statusCode == 401 && tryRefresh() -> {
                    val renewed = session.accessToken().orEmpty()
                    try {
                        source = api.playlist(renewed).toSource()
                    } catch (retry: EftvApi.ApiException) {
                        if (retry.isDeviceBlock()) throw DeviceBlockedException(retry.detail)
                    }
                }

                e.statusCode == 403 && e.isDeviceBlock() -> throw DeviceBlockedException(e.detail)

                e.statusCode == 403 -> Toast.makeText(
                    this@MainActivity,
                    R.string.subscription_inactive,
                    Toast.LENGTH_LONG,
                ).show()

                else -> Timber.w(
                    "Revalidacao indisponivel (HTTP %d); mantendo origem atual",
                    e.statusCode,
                )
            }
        } catch (e: DeviceBlockedException) {
            throw e
        } catch (e: Exception) {
            Timber.w(e, "Revalidacao falhou; mantendo a origem atual")
        }
    }

    private fun EftvApi.ApiException.isDeviceBlock(): Boolean =
        errorCode == "device_limit" || errorCode == "device_id_missing"

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

    private fun refreshCatalog(revalidateSource: Boolean = false) {
        if (!::repository.isInitialized) return
        if (refreshJob?.isActive == true) return

        val hasContent = hasCatalog
        if (!hasContent) showLoading()
        binding.swipeRefresh.isRefreshing = hasContent

        refreshJob = lifecycleScope.launch {
            try {
                if (revalidateSource) {
                    val skipAuth = intent.getBooleanExtra(EXTRA_SKIP_AUTH, false)
                    if (!skipAuth) {
                        try {
                            revalidateServerAccess()
                        } catch (e: DeviceBlockedException) {
                            showDeviceBlocked(e.message.orEmpty())
                            return@launch
                        }
                        // O vinculo pode ter mudado a origem (servidor x local).
                        repository = PlaylistRepository(this@MainActivity, source)
                    }
                }

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

    private suspend fun applyCatalog(metadata: CatalogStore.Metadata) {
        hasCatalog = metadata.total > 0
        catalogMetadata = metadata

        val groups = withContext(Dispatchers.IO) { repository.catalogStore.groups() }
        categoryAdapter.submit(
            groups = groups,
            favoritesLabel = getString(R.string.favorites),
            recentsLabel = getString(R.string.recents),
        )

        selectedCategory = CategoryAdapter.Category(CategoryAdapter.ALL)
        selectedMode = ChannelMode.ALL
        selectedGroup = null

        channelAdapter.setFavorites(withContext(Dispatchers.IO) { repository.catalogStore.favoriteUrls() })
        binding.toolbar.subtitle = buildSubtitle()
        binding.swipeRefresh.visibility = View.VISIBLE
        filterChannels(debounce = 0)
    }

    private fun buildSubtitle(shown: Int? = null): CharSequence {
        val (status, colorRes) = when {
            deviceBlocked -> getString(R.string.status_blocked) to R.color.error
            source.url.isBlank() -> getString(R.string.status_demo) to R.color.warning
            source.fromServer -> getString(R.string.status_online) to R.color.success
            else -> getString(R.string.status_local) to R.color.on_background
        }

        val meta = catalogMetadata
        val text = if (meta == null) {
            status
        } else {
            val number = NumberFormat.getIntegerInstance()
            val counts = if (shown != null && shown != meta.total) {
                getString(R.string.subtitle_filtered, number.format(shown), number.format(meta.total))
            } else {
                getString(R.string.subtitle_total, number.format(meta.total))
            }
            val time = if (meta.updatedAt > 0) {
                DateFormat.getTimeInstance(DateFormat.SHORT).format(Date(meta.updatedAt))
            } else {
                "--:--"
            }
            "$counts • $time • $status"
        }

        val dot = ContextCompat.getColor(this, colorRes)
        return SpannableString("●  $text").apply {
            setSpan(ForegroundColorSpan(dot), 0, 1, 0)
        }
    }

    private fun onCategorySelected(category: CategoryAdapter.Category) {
        selectedCategory = category
        selectedMode = category.mode
        selectedGroup = category.group
        binding.searchInput.clearFocus()
        hideKeyboard()
        filterChannels(debounce = 0)
    }

    private fun filterChannels(debounce: Long) {
        if (!::repository.isInitialized) return

        filterJob?.cancel()
        resetPaging()

        val group = selectedGroup
        val query = searchQuery.normalizedForSearch()
        val mode = selectedMode

        filterJob = lifecycleScope.launch {
            if (debounce > 0) delay(debounce)

            val total = withContext(Dispatchers.IO) {
                repository.catalogStore.count(group, query, mode)
            }
            if (!isActive) return@launch

            channelAdapter.reset(total)
            binding.channelList.scrollToPosition(0)
            binding.toolbar.subtitle = buildSubtitle(total)
            if (selectedCategory.mode != ChannelMode.ALL) {
                // Contagem de favoritos/historico sempre atualizada.
                channelAdapter.setFavorites(
                    withContext(Dispatchers.IO) { repository.catalogStore.favoriteUrls() }
                )
            }

            if (total > 0) {
                binding.stateContainer.visibility = View.GONE
                requestPage(0)
                requestPage(1)
                focusListIfTelevision()
            } else {
                showMessage(
                    message = emptyMessage(),
                    showProgress = false,
                    showRetry = false,
                    iconRes = emptyIcon(),
                )
            }
        }
    }

    private fun emptyMessage(): String = when {
        selectedMode == ChannelMode.FAVORITES -> getString(R.string.empty_favorites)
        selectedMode == ChannelMode.RECENTS -> getString(R.string.empty_recents)
        hasCatalog -> getString(R.string.empty_search)
        else -> getString(R.string.empty_catalog)
    }

    private fun emptyIcon(): Int = when (selectedMode) {
        ChannelMode.FAVORITES -> R.drawable.ic_star_outline
        ChannelMode.RECENTS -> R.drawable.ic_history
        else -> if (searchQuery.isNotBlank() || selectedGroup != null) {
            R.drawable.ic_search
        } else {
            R.drawable.ic_tv
        }
    }

    private fun requestPage(page: Int) {
        if (page < 0) return
        if (!::repository.isInitialized) return
        if (page * ChannelAdapter.PAGE_SIZE >= channelAdapter.itemCount) return
        if (channelAdapter.isPageLoaded(page)) return
        if (!loadingPages.add(page)) return

        val generation = queryGeneration
        val group = selectedGroup
        val query = searchQuery.normalizedForSearch()
        val mode = selectedMode

        val job = lifecycleScope.launch {
            try {
                val items = withContext(Dispatchers.IO) {
                    repository.catalogStore.page(
                        group = group,
                        query = query,
                        limit = ChannelAdapter.PAGE_SIZE,
                        offset = page * ChannelAdapter.PAGE_SIZE,
                        mode = mode,
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

    /** Salva/remove o canal dos favoritos e reflete na lista na hora. */
    private fun toggleFavorite(channel: Channel) {
        if (!::repository.isInitialized) return

        lifecycleScope.launch {
            val favorite = withContext(Dispatchers.IO) {
                val isFavorite = repository.catalogStore.isFavorite(channel.url)
                repository.catalogStore.setFavorite(channel.url, !isFavorite)
                !isFavorite
            }
            channelAdapter.setFavorites(
                withContext(Dispatchers.IO) { repository.catalogStore.favoriteUrls() }
            )
            Toast.makeText(
                this@MainActivity,
                if (favorite) R.string.favorite_saved else R.string.favorite_removed,
                Toast.LENGTH_SHORT,
            ).show()
            if (selectedMode == ChannelMode.FAVORITES) filterChannels(debounce = 0)
        }
    }

    private fun openPlayer(channel: Channel) {
        if (::repository.isInitialized) {
            // Historico em segundo plano; nao atrasa a abertura do canal.
            lifecycleScope.launch(Dispatchers.IO) {
                repository.catalogStore.markRecent(channel.url)
            }
        }

        binding.searchInput.clearFocus()
        hideKeyboard()
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
    // Estados e atalhos de navegacao
    // ------------------------------------------------------------------

    private fun showLoading() {
        showMessage(getString(R.string.loading_channels), showProgress = true, showRetry = false)
    }

    private fun showError(message: String?) {
        showMessage(
            message ?: getString(R.string.load_error),
            showProgress = false,
            showRetry = true,
            iconRes = R.drawable.ic_tv,
        )
    }

    private fun showMessage(
        message: String,
        showProgress: Boolean,
        showRetry: Boolean,
        iconRes: Int = 0,
    ) {
        binding.stateContainer.visibility = View.VISIBLE
        binding.stateProgress.visibility = if (showProgress) View.VISIBLE else View.GONE
        binding.stateIcon.visibility = if (iconRes != 0) View.VISIBLE else View.GONE
        if (iconRes != 0) binding.stateIcon.setImageResource(iconRes)
        binding.stateText.text = message
        binding.retryButton.visibility = if (showRetry) View.VISIBLE else View.GONE
    }

    private fun hideKeyboard() {
        val manager = getSystemService(Context.INPUT_METHOD_SERVICE) as? InputMethodManager
            ?: return
        if (manager.isActive) {
            manager.hideSoftInputFromWindow(binding.searchInput.windowToken, 0)
        }
    }

    // ------------------------------------------------------------------
    // Vinculo de aparelho
    // ------------------------------------------------------------------

    private fun showDeviceBlocked(message: String) {
        val detail = message.ifBlank { getString(R.string.device_blocked_default) }
        deviceBlocked = true
        channelAdapter.reset(0)
        binding.channelList.visibility = View.GONE
        binding.toolbar.subtitle = buildSubtitle()
        showMessage(
            message = getString(R.string.device_blocked_hint),
            showProgress = false,
            showRetry = false,
            iconRes = R.drawable.ic_devices,
        )
        MaterialAlertDialogBuilder(this)
            .setTitle(R.string.device_blocked_title)
            .setMessage(detail)
            .setPositiveButton(R.string.retry) { _, _ -> recreate() }
            .setNegativeButton(R.string.logout) { _, _ -> logout() }
            .setCancelable(false)
            .show()
    }

    private fun showDeviceDialog() {
        val token = session.accessToken()
        if (token.isNullOrBlank()) {
            goToLogin()
            return
        }

        lifecycleScope.launch {
            val access = try {
                withContext(Dispatchers.IO) { api.deviceAccess(token) }
            } catch (e: Exception) {
                Timber.w(e, "Falha ao consultar aparelhos")
                Toast.makeText(
                    this@MainActivity,
                    R.string.device_load_error,
                    Toast.LENGTH_LONG,
                ).show()
                return@launch
            }
            if (isFinishing) return@launch

            val current = access.devices.firstOrNull { it.current }
            val message = buildString {
                append(getString(R.string.device_limit_info, access.bound, access.limit))
                if (current != null) {
                    append("\n\n")
                    append(
                        getString(
                            R.string.device_current,
                            current.deviceName ?: getString(R.string.device_unnamed),
                        )
                    )
                }
            }

            MaterialAlertDialogBuilder(this@MainActivity)
                .setTitle(R.string.device_title)
                .setMessage(message)
                .setPositiveButton(R.string.device_revoke) { _, _ -> revokeCurrentDevice(token) }
                .setNegativeButton(R.string.close, null)
                .show()
        }
    }

    private fun revokeCurrentDevice(token: String) {
        lifecycleScope.launch {
            try {
                withContext(Dispatchers.IO) { api.revokeDevice(token) }
                Toast.makeText(
                    this@MainActivity,
                    R.string.device_revoked,
                    Toast.LENGTH_LONG,
                ).show()
            } catch (e: Exception) {
                Timber.w(e, "Falha ao desvincular o aparelho")
                Toast.makeText(
                    this@MainActivity,
                    e.message ?: getString(R.string.device_load_error),
                    Toast.LENGTH_LONG,
                ).show()
            }
        }
    }

    /** Em TV/controle remoto a lista precisa receber o foco para o D-pad funcionar. */
    private fun focusListIfTelevision() {
        if (!isTelevision) return
        binding.channelList.post {
            val manager = binding.channelList.layoutManager as? LinearLayoutManager ?: return@post
            val first = manager.findFirstVisibleItemPosition().coerceAtLeast(0)
            val view = binding.channelList.findViewHolderForAdapterPosition(first)?.itemView
            view?.requestFocus() ?: binding.channelList.requestFocus()
        }
    }

    companion object {
        const val EXTRA_SKIP_AUTH = "extra_skip_auth"

        /** Depois disso, o app tenta atualizar a lista em segundo plano. */
        private const val CACHE_TTL_MS = 6 * 60 * 60 * 1000L
    }

    private class DeviceBlockedException(message: String) : Exception(message)
}
