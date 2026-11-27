package com.eftv.android

import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Bundle
import android.text.SpannableString
import android.text.style.ForegroundColorSpan
import android.view.View
import android.view.WindowManager
import android.view.inputmethod.EditorInfo
import android.view.inputmethod.InputMethodManager
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.activity.result.contract.ActivityResultContracts
import androidx.core.content.ContextCompat
import androidx.core.widget.doAfterTextChanged
import androidx.lifecycle.lifecycleScope
import androidx.recyclerview.widget.GridLayoutManager
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import com.eftv.android.data.CatalogStore
import com.eftv.android.data.Channel
import com.eftv.android.data.ChannelKind
import com.eftv.android.data.ChannelMode
import com.eftv.android.data.AppScope
import com.eftv.android.data.DeviceIdentity
import com.eftv.android.data.LocalServer
import com.eftv.android.data.LogUtils
import com.eftv.android.data.NetworkInfo
import com.eftv.android.data.PlaylistRepository
import com.eftv.android.data.PlaylistSource
import com.eftv.android.data.SessionStore
import com.eftv.android.data.api.EftvApi
import com.eftv.android.data.normalizedForSearch
import com.eftv.android.databinding.ActivityMainBinding
import com.eftv.android.ui.CategoryGridAdapter
import com.eftv.android.ui.ChannelAdapter
import com.eftv.android.ui.ContinueAdapter
import com.google.android.material.dialog.MaterialAlertDialogBuilder
import com.google.android.material.tabs.TabLayout
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
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

class MainActivity : AppCompatActivity() {

    private lateinit var binding: ActivityMainBinding
    private val session by lazy { SessionStore(this) }
    private val device by lazy { DeviceIdentity(this) }
    private val api by lazy {
        EftvApi(deviceId = device.id, deviceName = device.name)
    }
    private lateinit var repository: PlaylistRepository
    private var source: PlaylistSource = PlaylistSource.local()
    private val channelAdapter = ChannelAdapter(
        ::openPlayer,
        { page -> requestPage(page) },
        ::toggleFavorite,
    )
    private val continueAdapter = ContinueAdapter(::openPlayer)

    private var selectedKind = ChannelKind.LIVE
    private var selectedCategory = CategoryGridAdapter.Selection(label = "")
    private var selectedMode = ChannelMode.ALL
    private var selectedGroup: String? = null
    private var catalogMetadata: CatalogStore.Metadata? = null

    /** Tela de categorias: devolve a escolha (grupo/modo) para a lista. */
    private val categoryPicker = registerForActivityResult(
        ActivityResultContracts.StartActivityForResult(),
    ) { result ->
        if (result.resultCode != RESULT_OK) return@registerForActivityResult
        val data = result.data ?: return@registerForActivityResult
        val label = data.getStringExtra(CategoriesActivity.RESULT_LABEL) ?: return@registerForActivityResult
        val mode = data.getStringExtra(CategoriesActivity.RESULT_MODE)
            ?.let { runCatching { ChannelMode.valueOf(it) }.getOrNull() }
            ?: ChannelMode.ALL
        onCategorySelected(
            CategoryGridAdapter.Selection(
                label = label,
                mode = mode,
                group = data.getStringExtra(CategoriesActivity.RESULT_GROUP),
            ),
        )
    }

    /** Aparelho barrado pelo servidor: nao mostra nem usa o catalogo local. */
    private var deviceBlocked = false

    /** Assinatura inativa: ao voltar para o app, tenta carregar de novo. */
    private var subscriptionBlocked = false
    private var searchQuery: String = ""
    private var hasCatalog = false

    /** Ultimo estado da preferencia de conteudo adulto (detecta mudanca). */
    private var adultEnabled = false

    /** Catalogo vem do servidor embutido no proprio aparelho. */
    private val localMode: Boolean
        get() = BuildConfig.LOCAL_MODE ||
            (BuildConfig.DEBUG && intent.getBooleanExtra(EXTRA_SKIP_AUTH, false))

    private var refreshJob: Job? = null
    private var importingCatalog = false
    private var importedCount = 0
    private var partialCatalogApplied = false
    private var lastProgressiveRefreshAt = 0L
    private var lastCatalogReportAt = 0L
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

        adultEnabled = SettingsActivity.isAdultContentEnabled(this)

        setupToolbar()
        setupKindTabs()
        setupLists()
        setupSearch()
        setupRefresh()

        // O servidor embutido (proxy de streams com DNS over HTTPS) sobe junto
        // com o app. Assim que ele responder, o player passa a abrir os canais
        // pelo proxy — necessario em operadoras que bloqueiam o DNS do
        // provedor nos dados moveis. Vale para todos os aparelhos.
        // A chamada aqui tambem cobre o caso em que o Android recusou iniciar
        // o servico com o app ainda em segundo plano.
        EftvServerService.start(this)
        lifecycleScope.launch {
            val ready = LocalServer.waitUntilReady(timeoutMs = 30_000)
            // As primeiras capas podem ter sido montadas antes do proxy subir.
            // Remonta os cards visiveis para aproveitar o DNS-over-HTTPS (ou o
            // fallback direto) sem o usuario precisar rolar a lista.
            if (ready && hasCatalog) {
                channelAdapter.notifyDataSetChanged()
                continueAdapter.notifyDataSetChanged()
            }
        }

        startCatalog()
        checkForUpdates()

        // Voltou pelo link eftv://open (checkout): abre direto a assinatura
        // para o cliente conferir se o pagamento foi reconhecido.
        if (intent.getBooleanExtra(EXTRA_OPEN_SUBSCRIPTION, false)) {
            openSubscription()
        } else {
            maybeShowTrialNudge()
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        // MainActivity ja estava aberta quando o link eftv://open chegou.
        if (intent.getBooleanExtra(EXTRA_OPEN_SUBSCRIPTION, false)) {
            openSubscription()
        }
    }

    /**
     * Atualizacao do app distribuido por APK.
     *
     * Sem isso cada correcao exigia reinstalar aparelho por aparelho. A
     * consulta e feita no maximo uma vez por dia e some quando o servidor
     * ainda nao tem APK publicado.
     */
    private fun checkForUpdates() {
        val prefs = getSharedPreferences(UPDATE_PREFS, MODE_PRIVATE)
        val lastCheck = prefs.getLong(UPDATE_LAST_CHECK, 0L)
        val now = System.currentTimeMillis()
        if (now - lastCheck < UPDATE_CHECK_INTERVAL_MS) return
        prefs.edit().putLong(UPDATE_LAST_CHECK, now).apply()

        lifecycleScope.launch {
            val info = runCatching { api.appVersion() }.getOrNull() ?: return@launch
            if (!info.configured || info.apkUrl.isBlank()) return@launch
            if (info.versionCode <= BuildConfig.VERSION_CODE) return@launch
            // O link vem do backend: só abre HTTPS em host público. Sem isso,
            // uma resposta adulterada poderia mandar o cliente baixar um APK
            // por HTTP (ou de um endereço local) sem qualquer aviso.
            if (!LogUtils.isSafeUpdateUrl(info.apkUrl)) {
                Timber.w(
                    "Atualizacao ignorada: URL nao segura (%s)",
                    LogUtils.redactUrl(info.apkUrl),
                )
                return@launch
            }
            if (isFinishing || isDestroyed) return@launch
            showUpdateDialog(info)
        }
    }

    private fun showUpdateDialog(info: EftvApi.AppVersionInfo) {
        val message = buildString {
            append(getString(R.string.update_available_message, info.versionName))
            if (info.notes.isNotBlank()) {
                append("\n\n")
                append(info.notes)
            }
        }
        val dialog = MaterialAlertDialogBuilder(this)
            .setTitle(R.string.update_available_title)
            .setMessage(message)
            .setCancelable(!info.mandatory)
            .setPositiveButton(R.string.update_now) { _, _ ->
                startApkUpdate(info)
            }
        if (!info.mandatory) {
            dialog.setNegativeButton(R.string.update_later, null)
        }
        dialog.show()
    }

    /**
     * Baixa o APK dentro do app e abre o instalador do Android.
     *
     * Antes o botao mandava para o navegador; o cliente muitas vezes nao
     * encontrava o arquivo baixado. Aqui a barra de progresso fica na propria
     * tela e o instalador abre apontando para o APK recem-baixado.
     */
    private fun startApkUpdate(info: EftvApi.AppVersionInfo) {
        if (!UpdateInstaller.canInstall(this)) {
            Toast.makeText(this, R.string.update_allow_install, Toast.LENGTH_LONG).show()
            UpdateInstaller.requestInstallPermission(this)
            return
        }

        val density = resources.displayMetrics.density
        val padding = (24 * density).toInt()
        val label = TextView(this).apply {
            text = getString(R.string.update_downloading)
        }
        val bar = android.widget.ProgressBar(
            this,
            null,
            android.R.attr.progressBarStyleHorizontal,
        ).apply {
            max = 100
            progress = 0
        }
        val content = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(padding, padding / 2, padding, 0)
            addView(label)
            addView(
                bar,
                LinearLayout.LayoutParams(
                    LinearLayout.LayoutParams.MATCH_PARENT,
                    LinearLayout.LayoutParams.WRAP_CONTENT,
                ).apply { topMargin = padding / 2 },
            )
        }

        val progressDialog = MaterialAlertDialogBuilder(this)
            .setTitle(R.string.update_downloading_title)
            .setView(content)
            .setCancelable(false)
            .create()
        progressDialog.show()

        lifecycleScope.launch {
            try {
                val file = UpdateInstaller.download(this@MainActivity, info.apkUrl) { percent ->
                    runOnUiThread {
                        if (percent < 0) {
                            bar.isIndeterminate = true
                        } else {
                            bar.progress = percent
                        }
                    }
                }
                progressDialog.dismiss()
                UpdateInstaller.install(this@MainActivity, file)
            } catch (e: Exception) {
                progressDialog.dismiss()
                Timber.w(e, "Falha ao baixar a atualizacao")
                Toast.makeText(
                    this@MainActivity,
                    R.string.update_download_failed,
                    Toast.LENGTH_LONG,
                ).show()
            }
        }
    }

    override fun onResume() {
        super.onResume()
        TvScreen.apply(this)

        // Voltou da tela de assinatura: se pagou, o catalogo precisa carregar
        // sem o usuario reiniciar o app.
        if (subscriptionBlocked && !localMode && session.hasSession()) {
            subscriptionBlocked = false
            startCatalog()
            return
        }
        if (!::repository.isInitialized || !hasCatalog) return

        val enabled = SettingsActivity.isAdultContentEnabled(this)
        val adultChanged = enabled != adultEnabled
        adultEnabled = enabled

        if (adultChanged) {
            // Preferencia mudou: recarrega a lista (e o filtro de categorias)
            // sem reiniciar o app.
            lifecycleScope.launch {
                val kind = selectedKind
                val groups = withContext(Dispatchers.IO) {
                    repository.catalogStore.groups(kind)
                }
                if (selectedKind != kind) return@launch

                // A opcao so tem efeito se a playlist trouxer canais adultos.
                if (enabled && groups.none { ChannelKind.isAdultGroup(it) }) {
                    Toast.makeText(
                        this@MainActivity,
                        R.string.adult_no_channels,
                        Toast.LENGTH_LONG,
                    ).show()
                }

                if (!enabled && ChannelKind.isAdultGroup(selectedGroup)) {
                    resetCategorySelection()
                }
                binding.categoryButton.text = selectedCategory.label
                filterChannels(debounce = 0)
            }
        } else if (selectedKind != ChannelKind.LIVE) {
            // Ao voltar do player, atualiza "min restantes" nas capas.
            refreshProgress()
        }
    }

    /** Atualiza o progresso das capas de filmes/series ja carregadas. */
    private fun refreshProgress() {
        refreshContinueWatching()
        val urls = channelAdapter.loadedUrls()
        if (urls.isEmpty()) return
        lifecycleScope.launch {
            val progress = withContext(Dispatchers.IO) {
                repository.catalogStore.progressFor(urls)
            }
            channelAdapter.updateProgress(progress)
        }
    }

    private fun setupToolbar() {
        binding.toolbar.inflateMenu(R.menu.menu_main)
        binding.toolbar.menu.findItem(R.id.action_open_web)?.isVisible = localMode
        binding.toolbar.menu.findItem(R.id.action_subscription)?.isVisible = !localMode
        binding.toolbar.menu.findItem(R.id.action_device)?.isVisible = !localMode
        binding.toolbar.menu.findItem(R.id.action_authorize_tv)?.isVisible = !localMode
        binding.toolbar.menu.findItem(R.id.action_install_tv)?.isVisible = !localMode
        binding.toolbar.menu.findItem(R.id.action_logout)?.isVisible = !localMode

        binding.toolbar.setOnMenuItemClickListener { item ->
            when (item.itemId) {
                R.id.action_refresh -> {
                    refreshCatalog(revalidateSource = !localMode)
                    true
                }

                R.id.action_open_web -> {
                    openLocalWeb()
                    true
                }

                R.id.action_settings -> {
                    startActivity(Intent(this@MainActivity, SettingsActivity::class.java))
                    true
                }

                R.id.action_subscription -> {
                    openSubscription()
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

                R.id.action_authorize_tv -> {
                    showAuthorizeTvDialog()
                    true
                }

                R.id.action_install_tv -> {
                    showInstallTvDialog()
                    true
                }

                else -> false
            }
        }

        // Toque longo no titulo abre as configuracoes escondidas
        binding.toolbar.setOnLongClickListener {
            startActivity(Intent(this@MainActivity, SettingsActivity::class.java))
            true
        }
    }

    private fun setupLists() {
        binding.channelList.apply {
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
        updateLayoutManager()
        setupContinueWatching()
        setupCategoryButton()
    }

    /** Carrossel horizontal com o VOD parado ("Continuar assistindo"). */
    private fun setupContinueWatching() {
        binding.continueList.apply {
            layoutManager = LinearLayoutManager(this@MainActivity, RecyclerView.HORIZONTAL, false)
            adapter = continueAdapter
        }
    }

    /**
     * Mostra o carrossel quando ha progresso salvo. Some na aba Ao vivo,
     * durante a busca e quando a lista ainda nao carregou.
     */
    private fun refreshContinueWatching() {
        val enabled = selectedKind != ChannelKind.LIVE &&
            searchQuery.isBlank() &&
            hasCatalog &&
            ::repository.isInitialized
        if (!enabled) {
            binding.continueWatchingLayout.visibility = View.GONE
            return
        }

        lifecycleScope.launch {
            val items = withContext(Dispatchers.IO) {
                repository.catalogStore.continueWatching()
                    // Grupos adultos so aparecem se a preferencia estiver ligada.
                    .filter { adultEnabled || !ChannelKind.isAdultGroup(it.group) }
            }
            // A aba ou a busca podem ter mudado durante a leitura do banco.
            if (selectedKind == ChannelKind.LIVE || searchQuery.isNotBlank()) return@launch

            continueAdapter.submitList(items)
            binding.continueWatchingLayout.visibility =
                if (items.isEmpty()) View.GONE else View.VISIBLE
        }
    }

    /** Abas principais: separa canais ao vivo de filmes e series. */
    private fun setupKindTabs() {
        val tabs = binding.kindTabs
        tabs.removeAllTabs()
        tabs.addTab(tabs.newTab().setText(R.string.kind_live).setTag(ChannelKind.LIVE), true)
        tabs.addTab(tabs.newTab().setText(R.string.kind_movies).setTag(ChannelKind.MOVIE))
        tabs.addTab(tabs.newTab().setText(R.string.kind_series).setTag(ChannelKind.SERIES))

        tabs.addOnTabSelectedListener(object : TabLayout.OnTabSelectedListener {
            override fun onTabSelected(tab: TabLayout.Tab) {
                val kind = tab.tag as? ChannelKind ?: return
                if (kind == selectedKind && hasCatalog) return

                selectedKind = kind
                resetCategorySelection()
                updateLayoutManager()
                binding.categoryButton.text = selectedCategory.label

                if (!::repository.isInitialized || !hasCatalog) return
                // O botao mostra a categoria (sempre "Todos" ao trocar de aba).
                binding.categoryButton.text = selectedCategory.label
                filterChannels(debounce = 0)
                refreshContinueWatching()
            }

            override fun onTabUnselected(tab: TabLayout.Tab) = Unit
            override fun onTabReselected(tab: TabLayout.Tab) = Unit
        })
    }

    /**
     * Ao vivo usa lista horizontal; filmes/series usam grade de capas.
     * A troca de layout manager limpa as paginas antigas para nao misturar
     * itens de tipos diferentes durante a transicao.
     */
    private fun updateLayoutManager() {
        val columns = when {
            selectedKind == ChannelKind.LIVE -> 1
            isTelevision -> 3
            else -> 2
        }
        channelAdapter.setKind(selectedKind)
        channelAdapter.reset(0)
        binding.channelList.layoutManager =
            if (columns > 1) GridLayoutManager(this, columns) else LinearLayoutManager(this)
    }

    /**
     * "Autorizar TV": a TV mostra um codigo e o assinante confirma aqui, onde
     * ja esta logado. Evita digitar e-mail e senha no controle remoto.
     */
    /**
     * Link curto para instalar o APK na TV.
     *
     * A TV nao consegue "receber" o app por perto: o cliente digita este
     * endereco no Downloader (Fire TV) ou no navegador do box e a TV baixa o
     * APK. O backend responde com 302 direto no arquivo (/tv e /app/tv).
     */
    private fun installTvUrl(): String? {
        val base = BuildConfig.API_BASE_URL.trim().trimEnd('/')
        if (base.isBlank() || base.contains("127.0.0.1") || base.contains("localhost")) {
            return null
        }
        return "$base/tv"
    }

    private fun showInstallTvDialog() {
        val url = installTvUrl()
        if (url == null) {
            Toast.makeText(this, R.string.install_tv_unavailable, Toast.LENGTH_LONG).show()
            return
        }

        val density = resources.displayMetrics.density
        val padding = (24 * density).toInt()
        val content = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(padding, padding, padding, 0)
        }

        content.addView(
            TextView(this).apply {
                setText(R.string.install_tv_steps)
                setTextColor(ContextCompat.getColor(this@MainActivity, R.color.on_background))
                textSize = 14f
            },
        )

        content.addView(
            TextView(this).apply {
                text = url
                setTextColor(ContextCompat.getColor(this@MainActivity, R.color.primary))
                textSize = 17f
                typeface = android.graphics.Typeface.MONOSPACE
                setTextIsSelectable(true)
                setPadding(0, (16 * density).toInt(), 0, 0)
            },
        )

        MaterialAlertDialogBuilder(this)
            .setTitle(R.string.install_tv_title)
            .setView(content)
            .setPositiveButton(R.string.install_tv_copy) { _, _ ->
                val clipboard =
                    getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
                clipboard.setPrimaryClip(
                    ClipData.newPlainText(getString(R.string.install_tv_title), url),
                )
                Toast.makeText(this, R.string.install_tv_copied, Toast.LENGTH_SHORT).show()
            }
            .setNegativeButton(android.R.string.cancel, null)
            .show()
    }

    private fun showAuthorizeTvDialog() {
        val input = EditText(this).apply {
            hint = getString(R.string.authorize_tv_hint)
            inputType = android.text.InputType.TYPE_CLASS_TEXT or
                android.text.InputType.TYPE_TEXT_FLAG_CAP_CHARACTERS
            filters = arrayOf(android.text.InputFilter.LengthFilter(9))
            setTextColor(ContextCompat.getColor(this@MainActivity, R.color.on_background))
            setPadding(56, 32, 56, 16)
            textSize = 22f
            gravity = android.view.Gravity.CENTER
        }
        val container = android.widget.FrameLayout(this).apply { addView(input) }

        val dialog = MaterialAlertDialogBuilder(this)
            .setTitle(R.string.authorize_tv_title)
            .setView(container)
            .setPositiveButton(R.string.authorize_tv_confirm, null)
            .setNegativeButton(android.R.string.cancel, null)
            .create()

        dialog.setOnShowListener {
            dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener {
                val code = input.text?.toString().orEmpty().replace(" ", "").trim()
                if (code.length < 8) {
                    input.error = getString(R.string.authorize_tv_invalid)
                    return@setOnClickListener
                }
                lifecycleScope.launch {
                    val token = validToken() ?: run {
                        Toast.makeText(
                            this@MainActivity,
                            R.string.tv_login_unavailable,
                            Toast.LENGTH_LONG,
                        ).show()
                        return@launch
                    }
                    try {
                        val message = api.approveDeviceCode(token, code)
                        dialog.dismiss()
                        Toast.makeText(
                            this@MainActivity,
                            message.ifBlank { getString(R.string.authorize_tv_done) },
                            Toast.LENGTH_LONG,
                        ).show()
                    } catch (e: EftvApi.ApiException) {
                        input.error = e.detail
                    } catch (e: Exception) {
                        Timber.w(e, "Falha ao autorizar a TV")
                        Toast.makeText(
                            this@MainActivity,
                            R.string.tv_login_unavailable,
                            Toast.LENGTH_LONG,
                        ).show()
                    }
                }
            }
        }
        dialog.show()
    }

    /** Token valido (renova com o refresh se o curto expirou). */
    private suspend fun validToken(): String? {
        val token = session.accessToken() ?: return null
        if (!session.isAccessTokenExpired()) return token
        if (!tryRefresh()) return null
        return session.accessToken()
    }

    private fun setupCategoryButton() {        binding.categoryButton.setOnClickListener {
            openCategoryPicker()
        }
        setupAlphabetBar()
    }

    /**
     * Barra A-Z: em 2 mil canais, achar "S" arrastando a lista nao funciona.
     * So aparece na lista de canais ao vivo, fora da TV (la quem navega e o
     * controle remoto, e o foco ja resolve).
     */
    private fun setupAlphabetBar() {
        binding.alphabetBar.onLetterPicked = ::jumpToLetter
    }

    private fun jumpToLetter(letter: Char) {
        if (!::repository.isInitialized) return
        if (letter == '#') {
            binding.channelList.scrollToPosition(0)
            return
        }
        val group = selectedGroup
        val query = searchQuery.normalizedForSearch()
        val mode = selectedMode
        val kind = selectedKind
        val excludeAdults = shouldExcludeAdults()

        lifecycleScope.launch {
            val index = runCatching {
                withContext(Dispatchers.IO) {
                    repository.catalogStore.firstIndexForLetter(
                        group = group,
                        query = query,
                        mode = mode,
                        kind = kind,
                        excludeAdults = excludeAdults,
                        letter = letter.lowercaseChar(),
                    )
                }
            }.getOrElse {
                Timber.w(it, "Nao foi possivel pular para a letra %s", letter)
                return@launch
            }
            if (index >= 0) {
                (binding.channelList.layoutManager as? LinearLayoutManager)
                    ?.scrollToPositionWithOffset(index, 0)
                    ?: binding.channelList.scrollToPosition(index)
            }
        }
    }

    private fun updateAlphabetBar(total: Int) {
        val groupedSeries = selectedKind == ChannelKind.SERIES && selectedMode == ChannelMode.ALL
        val visible = !isTelevision &&
            selectedKind == ChannelKind.LIVE &&
            !groupedSeries &&
            binding.channelList.layoutManager is LinearLayoutManager &&
            total >= ALPHABET_MIN_ITEMS
        binding.alphabetBar.visibility = if (visible) View.VISIBLE else View.GONE
    }

    /** Abre a tela de categorias do tipo ativo (canais, filmes ou series). */
    private fun openCategoryPicker() {
        if (!hasCatalog) return
        val intent = Intent(this, CategoriesActivity::class.java)
            .putExtra(CategoriesActivity.EXTRA_KIND, selectedKind.name)
            .putExtra(CategoriesActivity.EXTRA_MODE, selectedMode.name)
            .putExtra(CategoriesActivity.EXTRA_GROUP, selectedGroup)
        categoryPicker.launch(intent)
    }

    private fun setupSearch() {
        binding.searchInput.doAfterTextChanged { text ->
            searchQuery = text?.toString().orEmpty()
            // Digitando, o carrossel sai da frente da busca na hora.
            refreshContinueWatching()
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
        binding.swipeRefresh.setOnRefreshListener {
            refreshCatalog(revalidateSource = !localMode)
        }
        binding.retryButton.setOnClickListener {
            if (!localMode || LocalServer.isReady()) {
                refreshCatalog(revalidateSource = !localMode)
            } else {
                startCatalog()
            }
        }
    }

    // ------------------------------------------------------------------
    // Catalogo
    // ------------------------------------------------------------------

    /**
     * Resolve a origem do catalogo: servidor (assinante autorizado) ou lista
     * local. Nunca bloqueia o app por causa do backend.
     */
    private fun startCatalog() {
        lifecycleScope.launch {
            showLoading()
            source = if (localMode) {
                // O servidor sobe junto com o app; espera responder antes de
                // baixar a playlist local.
                if (!LocalServer.waitUntilReady()) {
                    showError(getString(R.string.server_not_ready))
                    return@launch
                }
                if (LocalServer.playlistCount() == 0) {
                    showMessage(
                        message = getString(R.string.server_no_playlist),
                        showProgress = false,
                        showRetry = false,
                        iconRes = R.drawable.ic_tv,
                    )
                    return@launch
                }
                LocalServer.playlistSource()
            } else {
                try {
                    resolveSource()
                } catch (e: DeviceBlockedException) {
                    showDeviceBlocked(e.message.orEmpty())
                    return@launch
                } catch (e: SubscriptionExpiredException) {
                    showSubscriptionInactive(e.message.orEmpty())
                    return@launch
                } catch (e: CatalogErrorException) {
                    showCatalogError(e.message.orEmpty())
                    return@launch
                }
            }
            repository = PlaylistRepository(this@MainActivity, source)
            loadCatalog()
        }
    }

    private suspend fun resolveSource(): PlaylistSource {
        val token = session.accessToken()
        // Produção: sem token = vai para login, não para demo/local
        if (token.isNullOrBlank()) {
            goToLogin()
            // Retorna source dummy; o fluxo será interrompido pelo finish() no goToLogin()
            return PlaylistSource.local()
        }

        return try {
            try {
                api.playlist(token).toSource()
            } catch (e: Exception) {
                if (e is CancellationException) throw e
                // 4xx (login/blocked/expired) nao muda com uma segunda chamada.
                if (e is EftvApi.ApiException && e.statusCode in 400..499 && e.statusCode != 408) {
                    throw e
                }
                // Render free dormindo: primeira requisicao pode expirar.
                Timber.w(e, "Backend frio/indisponivel; tentando buscar a playlist de novo")
                delay(2_000)
                api.playlist(token).toSource()
            }
        } catch (e: EftvApi.ApiException) {
            when (e.statusCode) {
                401 -> {
                    if (tryRefresh()) {
                        try {
                            api.playlist(session.accessToken().orEmpty()).toSource()
                        } catch (retry: EftvApi.ApiException) {
                            if (retry.isDeviceBlock()) throw DeviceBlockedException(retry.detail)
                            // Assinatura inativa: o usuario vai direto para a
                            // tela de pagamento, em vez de ver "aparelho".
                            throw SubscriptionExpiredException(retry.detail)
                        }
                    } else {
                        session.clear()
                        goToLogin()
                        return PlaylistSource.local()
                    }
                }

                403 -> {
                    if (e.isDeviceBlock()) {
                        throw DeviceBlockedException(e.detail)
                    }
                    // Assinatura vencida ou e-mail nao confirmado.
                    throw SubscriptionExpiredException(e.detail)
                }

                503 -> {
                    Timber.w("Servidor sem playlist configurada (503)")
                    throw CatalogErrorException(
                        getString(R.string.server_unavailable)
                    )
                }

                else -> {
                    Timber.w("Erro HTTP %d ao buscar playlist", e.statusCode)
                    throw CatalogErrorException(
                        getString(R.string.catalog_http_error, e.statusCode)
                    )
                }
            }
        } catch (e: CancellationException) {
            throw e
        } catch (e: Exception) {
            Timber.e(e, "Falha inesperada ao resolver source")
            throw CatalogErrorException(getString(R.string.catalog_network_error))
        }
    }

    private suspend fun tryRefresh(): Boolean {
        val refreshToken = session.refreshToken()
        if (refreshToken.isNullOrBlank()) return false

        return try {
            val tokens = api.refresh(refreshToken)
            session.save(tokens, session.email().orEmpty(), session.isEmailVerified())
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
        // Atualizacao automatica nao mostra o indicador de "puxar para atualizar":
        // ele ficava girando sobre a lista. O gesto do usuario cuida do proprio spinner.

        refreshJob = lifecycleScope.launch {
            try {
                if (localMode && LocalServer.playlistCount() == 0) {
                    binding.swipeRefresh.isRefreshing = false
                    showMessage(
                        message = getString(R.string.server_no_playlist),
                        showProgress = false,
                        showRetry = false,
                        iconRes = R.drawable.ic_tv,
                    )
                    return@launch
                }

                if (revalidateSource && !localMode) {
                    try {
                        revalidateServerAccess()
                    } catch (e: DeviceBlockedException) {
                        showDeviceBlocked(e.message.orEmpty())
                        return@launch
                    }
                    // O vinculo pode ter mudado a origem (servidor x local).
                    repository = PlaylistRepository(this@MainActivity, source)
                }

                importingCatalog = true
                importedCount = 0
                partialCatalogApplied = false
                lastProgressiveRefreshAt = 0L
                if (!hasContent && !isFinishing) {
                    binding.stateText.text = getString(R.string.importing_channels, "0")
                } else {
                    Toast.makeText(
                        this@MainActivity,
                        R.string.import_started,
                        Toast.LENGTH_LONG,
                    ).show()
                }
                binding.toolbar.subtitle = buildSubtitle()

                val result = repository.refresh { count ->
                    runOnUiThread {
                        importingCatalog = true
                        importedCount = count
                        if (!hasContent && !isFinishing) {
                            binding.stateText.text = getString(
                                R.string.importing_channels,
                                NumberFormat.getIntegerInstance().format(count),
                            )
                        }
                        if (!isFinishing) {
                            binding.toolbar.subtitle = buildSubtitle()
                            // Na primeira leva, abre a lista com o que ja
                            // chegou. Depois so atualiza as paginas carregadas:
                            // reaplicar o catalogo inteiro reiniciava a consulta
                            // da aba Series e deixava a tela em "Carregando...".
                            if (!partialCatalogApplied) {
                                partialCatalogApplied = true
                                revealImportedBatch()
                            } else {
                                refreshImportedBatch()
                            }
                        }
                    }
                }
                importingCatalog = false
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
                importingCatalog = false
                if (!isFinishing) binding.toolbar.subtitle = buildSubtitle()
                Timber.e(e, "Falha ao carregar o catalogo")
                reportCatalogFailure(e)
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

    /**
     * Envia a falha do catálogo para o backend com o tipo de rede.
     *
     * Sem isso, "não funciona nos dados móveis" chega sem dizer se o problema
     * é DNS do provedor, bloqueio da operadora ou o backend. O relato é
     * mascarado (sem a URL do provedor) e limitado a um por hora por sessão.
     */
    private fun reportCatalogFailure(e: Exception) {
        val agora = System.currentTimeMillis()
        if (agora - lastCatalogReportAt < CATALOG_REPORT_INTERVAL_MS) return
        lastCatalogReportAt = agora
        val rede = NetworkInfo.label(this)
        AppScope.io.launch {
            runCatching {
                api.reportCrash(
                    message = "catalogo [$rede] ${e.javaClass.simpleName}: " +
                        LogUtils.redactText(e.message.orEmpty()),
                    stacktrace = LogUtils.redactThrowable(e),
                    appVersion = BuildConfig.VERSION_NAME,
                    device = android.os.Build.MODEL.orEmpty(),
                    android = android.os.Build.VERSION.RELEASE.orEmpty(),
                )
            }
        }
    }

    private suspend fun applyCatalog(
        metadata: CatalogStore.Metadata,
        keepSelection: Boolean = false,
    ) {
        hasCatalog = metadata.total > 0
        catalogMetadata = metadata
        deviceBlocked = false
        subscriptionBlocked = false

        if (!keepSelection) resetCategorySelection()

        binding.categoryButton.text = selectedCategory.label

        channelAdapter.setFavorites(withContext(Dispatchers.IO) { repository.catalogStore.favoriteUrls() })
        updateLayoutManager()
        binding.channelList.visibility = View.VISIBLE
        binding.toolbar.subtitle = buildSubtitle()
        binding.swipeRefresh.visibility = View.VISIBLE
        filterChannels(debounce = 0)
        refreshContinueWatching()
    }

    /**
     * Libera o primeiro lote commitado: o usuario entra na lista antes do fim
     * da importacao e ja pode assistir ao que chegou.
     */
    private fun revealImportedBatch() {
        lifecycleScope.launch {
            val partial = withContext(Dispatchers.IO) { repository.partial() }
            if (!isActive || partial == null || partial.total <= 0) return@launch
            applyCatalog(partial, keepSelection = true)
            lastProgressiveRefreshAt = System.currentTimeMillis()
        }
    }

    /**
     * Faz os lotes seguintes aparecerem sem perder a posicao da lista.
     * so consulta a contagem e as paginas ja carregadas; nunca chama
     * [filterChannels], que reiniciaria a paginacao e a aba Series.
     */
    private fun refreshImportedBatch() {
        if (!hasCatalog || !::repository.isInitialized || isFinishing) return
        val now = System.currentTimeMillis()
        if (now - lastProgressiveRefreshAt < 1_000L) return
        lastProgressiveRefreshAt = now

        lifecycleScope.launch {
            val store = repository.catalogStore
            val group = selectedGroup
            val query = searchQuery.normalizedForSearch()
            val mode = selectedMode
            val kind = selectedKind
            val excludeAdults = shouldExcludeAdults()
            val total = withContext(Dispatchers.IO) {
                if (excludeAdults) {
                    store.countExcludingAdults(group, query, mode, kind)
                } else {
                    store.count(group, query, mode, kind)
                }
            }
            if (!isActive) return@launch

            channelAdapter.updateTotal(total)
            binding.toolbar.subtitle = buildSubtitle(total)
            // Atualiza somente o que esta na tela. As paginas ainda nao vistas
            // continuam com o placeholder e sao carregadas ao rolar.
            channelAdapter.loadedPages().forEach { page -> requestPage(page, force = true) }
            refreshContinueWatching()
        }
    }

    /**
     * Reinicia a selecao de categoria.
     * Grupos adultos so aparecem quando liberados nas configuracoes.
     */
    private fun resetCategorySelection() {
        selectedCategory = CategoryGridAdapter.Selection(
            label = getString(R.string.categories_all),
            mode = ChannelMode.ALL,
            group = null,
        )
        selectedMode = ChannelMode.ALL
        selectedGroup = null
    }

    private fun buildSubtitle(shown: Int? = null): CharSequence {
        if (importingCatalog) {
            val text = getString(
                R.string.importing_catalog,
                NumberFormat.getIntegerInstance().format(importedCount),
            )
            val dot = ContextCompat.getColor(this, R.color.warning)
            return SpannableString("●  $text").apply {
                setSpan(ForegroundColorSpan(dot), 0, 1, 0)
            }
        }
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
            val count = shown ?: meta.total
            val counts = getString(
                R.string.subtitle_total_kind,
                number.format(count),
                kindNoun(count),
            )
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

    /** "1 canal" / "2 canais", "1 filme" / "2 filmes"... */
    private fun kindNoun(count: Int): String = when (selectedKind) {
        ChannelKind.LIVE -> getString(
            if (count == 1) R.string.kind_live_singular else R.string.kind_live_plural,
        )
        ChannelKind.MOVIE -> getString(
            if (count == 1) R.string.kind_movies_singular else R.string.kind_movies_plural,
        )
        ChannelKind.SERIES -> getString(
            if (count == 1) R.string.kind_series_singular else R.string.kind_series_plural,
        )
    }

    private fun onCategorySelected(category: CategoryGridAdapter.Selection) {
        selectedCategory = category
        selectedMode = category.mode
        selectedGroup = category.group
        binding.categoryButton.text = category.label
        binding.searchInput.clearFocus()
        hideKeyboard()
        filterChannels(debounce = 0)
    }

    /** Se verdadeiro, exclui conteudo adulto de listagens e buscas. */
    private fun shouldExcludeAdults(): Boolean =
        !SettingsActivity.isAdultContentEnabled(this)

    private fun filterChannels(debounce: Long) {
        if (!::repository.isInitialized) return

        filterJob?.cancel()
        resetPaging()

        val group = selectedGroup
        val query = searchQuery.normalizedForSearch()
        val mode = selectedMode
        val kind = selectedKind
        val excludeAdults = shouldExcludeAdults()

        filterJob = lifecycleScope.launch {
            if (debounce > 0) delay(debounce)

            val total = withContext(Dispatchers.IO) {
                if (excludeAdults) {
                    repository.catalogStore.countExcludingAdults(group, query, mode, kind)
                } else {
                    repository.catalogStore.count(group, query, mode, kind)
                }
            }
            if (!isActive) return@launch

            channelAdapter.setKind(kind)
            channelAdapter.reset(total)
            binding.channelList.scrollToPosition(0)
            updateAlphabetBar(total)
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
        !hasCatalog -> getString(R.string.empty_catalog)
        searchQuery.isNotBlank() || selectedGroup != null -> getString(R.string.empty_search)
        selectedKind == ChannelKind.MOVIE -> getString(R.string.empty_movies)
        selectedKind == ChannelKind.SERIES -> getString(R.string.empty_series)
        else -> getString(R.string.empty_live)
    }

    private fun emptyIcon(): Int = when {
        selectedMode == ChannelMode.FAVORITES -> R.drawable.ic_star_outline
        selectedMode == ChannelMode.RECENTS -> R.drawable.ic_history
        searchQuery.isNotBlank() || selectedGroup != null -> R.drawable.ic_search
        selectedKind == ChannelKind.MOVIE -> R.drawable.ic_movie
        selectedKind == ChannelKind.SERIES -> R.drawable.ic_series
        else -> R.drawable.ic_tv
    }

    private fun requestPage(page: Int, force: Boolean = false) {
        if (page < 0) return
        if (!::repository.isInitialized) return
        if (page * ChannelAdapter.PAGE_SIZE >= channelAdapter.itemCount) return
        if (!force && channelAdapter.isPageLoaded(page)) return
        if (loadingPages.contains(page)) {
            if (!force) return
            pageJobs[page]?.cancel()
        }
        loadingPages.add(page)

        val generation = queryGeneration
        val group = selectedGroup
        val query = searchQuery.normalizedForSearch()
        val mode = selectedMode
        val kind = selectedKind
        val excludeAdults = shouldExcludeAdults()

        val job = lifecycleScope.launch {
            try {
                val items = withContext(Dispatchers.IO) {
                    if (excludeAdults) {
                        repository.catalogStore.pageExcludingAdults(
                            group = group,
                            query = query,
                            limit = ChannelAdapter.PAGE_SIZE,
                            offset = page * ChannelAdapter.PAGE_SIZE,
                            mode = mode,
                            kind = kind,
                        )
                    } else {
                        repository.catalogStore.page(
                            group = group,
                            query = query,
                            limit = ChannelAdapter.PAGE_SIZE,
                            offset = page * ChannelAdapter.PAGE_SIZE,
                            mode = mode,
                            kind = kind,
                        )
                    }
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

    /** Card de serie abre temporadas e episodios; o resto vai direto ao player. */
    private fun openSeries(channel: Channel) {
        binding.searchInput.clearFocus()
        hideKeyboard()
        startActivity(
            Intent(this, SeriesActivity::class.java).apply {
                putExtra(SeriesActivity.EXTRA_KEY, channel.seriesKey)
                putExtra(SeriesActivity.EXTRA_TITLE, channel.seriesTitle.ifBlank { channel.name })
                putExtra(SeriesActivity.EXTRA_LOGO, channel.logo)
                putExtra(
                    SeriesActivity.EXTRA_USER_AGENT,
                    channel.userAgent ?: source.userAgent,
                )
            }
        )
    }

    private fun openPlayer(channel: Channel) {
        if (channel.isSeriesCard) {
            openSeries(channel)
            return
        }

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
                putExtra(PlayerActivity.EXTRA_KIND, channel.kind.name)
            }
        )
    }

    // ------------------------------------------------------------------
    // Estados e atalhos de navegacao
    // ------------------------------------------------------------------

    // ------------------------------------------------------------------
    // Servidor local / playlists
    // ------------------------------------------------------------------

    private fun openLocalWeb() {
        try {
            startActivity(Intent(Intent.ACTION_VIEW, Uri.parse("${LocalServer.BASE_URL}/")))
        } catch (_: Exception) {
            Toast.makeText(this, R.string.server_not_ready, Toast.LENGTH_LONG).show()
        }
    }

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
            .setNeutralButton(R.string.device_revoke_all) { _, _ -> revokeAllDevicesAndRetry() }
            .setNegativeButton(R.string.logout) { _, _ -> logout() }
            .setCancelable(false)
            .show()
    }

    /**
     * Libera as vagas de aparelho da conta e tenta entrar de novo.
     *
     * Quem trocou de celular ou reinstalou o app fica com o aparelho antigo
     * vinculado e ve "Assinatura em uso". Assim o proprio usuario resolve,
     * sem depender de suporte.
     */
    private fun revokeAllDevicesAndRetry() {
        val token = session.accessToken()
        if (token.isNullOrBlank()) {
            goToLogin()
            return
        }
        lifecycleScope.launch {
            try {
                withContext(Dispatchers.IO) { api.revokeAllDevices(token) }
                Toast.makeText(
                    this@MainActivity,
                    R.string.device_revoke_all_done,
                    Toast.LENGTH_LONG,
                ).show()
                recreate()
            } catch (e: Exception) {
                Timber.w(e, "Falha ao liberar aparelhos")
                Toast.makeText(
                    this@MainActivity,
                    e.message ?: getString(R.string.device_load_error),
                    Toast.LENGTH_LONG,
                ).show()
            }
        }
    }

    /**
     * Assinatura inativa/vencida: leva o cliente direto ao pagamento.
     *
     * Antes o app mostrava "Assinatura em uso", que e um erro de aparelho.
     * Quem esta no fim do trial precisa ver o preco e o botao de assinar.
     */
    private fun showSubscriptionInactive(message: String) {
        val detail = message.ifBlank { getString(R.string.subscription_inactive_message) }
        deviceBlocked = true
        subscriptionBlocked = true
        channelAdapter.reset(0)
        binding.channelList.visibility = View.GONE
        binding.toolbar.subtitle = buildSubtitle()
        showMessage(
            message = getString(R.string.subscription_inactive_hint),
            showProgress = false,
            showRetry = false,
            iconRes = R.drawable.ic_tv,
        )
        MaterialAlertDialogBuilder(this)
            .setTitle(R.string.subscription_inactive_title)
            .setMessage(detail)
            .setPositiveButton(R.string.subscription_subscribe_now) { _, _ -> openSubscription() }
            .setNegativeButton(R.string.logout) { _, _ -> logout() }
            .setCancelable(false)
            .show()
    }

    /** Falha de servidor/rede que nao e assinatura nem aparelho. */
    private fun showCatalogError(message: String) {
        channelAdapter.reset(0)
        binding.channelList.visibility = View.GONE
        showMessage(
            message = message.ifBlank { getString(R.string.load_error) },
            showProgress = false,
            showRetry = false,
            iconRes = R.drawable.ic_tv,
        )
        MaterialAlertDialogBuilder(this)
            .setTitle(R.string.catalog_error_title)
            .setMessage(message.ifBlank { getString(R.string.load_error) })
            .setPositiveButton(R.string.retry) { _, _ -> startCatalog() }
            .setNegativeButton(R.string.close) { _, _ -> finish() }
            .setCancelable(false)
            .show()
    }

    /**
     * Lembrete de fim do teste grátis.
     *
     * O backend manda email, mas boa parte dos clientes não abre. O aviso
     * dentro do app (no máximo uma vez por dia, nos últimos dias do teste)
     * aumenta a conversão para o plano de R$ 19,90 e evita a surpresa de
     * descobrir o vencimento só quando o canal para de abrir.
     */
    private fun maybeShowTrialNudge() {
        if (localMode || !session.hasSession()) return
        val prefs = getSharedPreferences(NUDGE_PREFS, MODE_PRIVATE)
        val today = SimpleDateFormat("yyyyMMdd", Locale.US).format(Date())
        if (prefs.getString(NUDGE_LAST_DAY, null) == today) return

        lifecycleScope.launch {
            val token = validToken() ?: return@launch
            val overview = runCatching {
                withContext(Dispatchers.IO) { api.subscriptionOverview(token) }
            }.getOrNull() ?: return@launch

            if (isFinishing || isDestroyed) return@launch
            if (!overview.hasAccess || overview.status != "trial") return@launch
            if (overview.daysRemaining > TRIAL_NUDGE_DAYS) return@launch

            prefs.edit().putString(NUDGE_LAST_DAY, today).apply()
            val days = resources.getQuantityString(
                R.plurals.subscription_days_remaining,
                overview.daysRemaining,
                overview.daysRemaining,
            )
            val price = NumberFormat.getCurrencyInstance(Locale("pt", "BR"))
                .format(overview.priceCents / 100.0)

            MaterialAlertDialogBuilder(this@MainActivity)
                .setTitle(R.string.trial_nudge_title)
                .setMessage(getString(R.string.trial_nudge_message, days, price))
                .setPositiveButton(R.string.subscription_subscribe_now) { _, _ ->
                    openSubscription()
                }
                .setNegativeButton(R.string.trial_nudge_later, null)
                .show()
        }
    }

    private fun openSubscription() {
        startActivity(Intent(this@MainActivity, SubscriptionActivity::class.java))
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

        /** Abre a tela "Minha assinatura" ao entrar (retorno do checkout). */
        const val EXTRA_OPEN_SUBSCRIPTION = "extra_open_subscription"

        /** Aviso de fim do teste: uma vez por dia nos últimos 3 dias. */
        private const val TRIAL_NUDGE_DAYS = 3
        private const val NUDGE_PREFS = "eftv_nudge"
        private const val NUDGE_LAST_DAY = "last_day"

        /** Depois disso, o app tenta atualizar a lista em segundo plano. */
        private const val CACHE_TTL_MS = 6 * 60 * 60 * 1000L

        /** Abaixo disso a barra A-Z so atrapalha (a lista ja cabe na tela). */
        private const val ALPHABET_MIN_ITEMS = 80

        /** Atualizacao do app: consulta no maximo uma vez por dia. */
        private const val UPDATE_PREFS = "eftv_updates"
        private const val UPDATE_LAST_CHECK = "last_check"
        private const val UPDATE_CHECK_INTERVAL_MS = 24 * 60 * 60 * 1000L

        /** No maximo um relato de falha do catalogo por hora. */
        private const val CATALOG_REPORT_INTERVAL_MS = 60 * 60 * 1000L
    }

    private class DeviceBlockedException(message: String) : Exception(message)

    /** Assinatura vencida/inativa: oferece o pagamento em vez de "assinatura em uso". */
    private class SubscriptionExpiredException(message: String) : Exception(message)

    /** Falha de servidor/rede ao carregar o catalogo (nao e bloqueio). */
    private class CatalogErrorException(message: String) : Exception(message)
}
