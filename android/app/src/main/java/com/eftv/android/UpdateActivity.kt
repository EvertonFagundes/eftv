package com.eftv.android

import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.provider.Settings
import android.view.View
import android.view.WindowManager
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import com.eftv.android.data.DeviceIdentity
import com.eftv.android.data.LogUtils
import com.eftv.android.data.api.EftvApi
import com.eftv.android.databinding.ActivityUpdateBinding
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.launch
import timber.log.Timber
import java.io.File

/**
 * Tela de atualizacao do APK.
 *
 * O app e distribuido fora da Play Store, entao a atualizacao precisa ser
 * baixada e instalada por ele mesmo. Esta tela existe para o cliente conseguir
 * pedir a atualizacao a qualquer momento (menu ou Configuracoes), em vez de
 * esperar o aviso diario ou procurar um APK novo na internet.
 *
 * O fluxo tambem sobrevive a ida ao painel de "instalar apps desconhecidos":
 * ao voltar, se a permissao foi concedida, o download continua sozinho.
 */
class UpdateActivity : AppCompatActivity() {

    private lateinit var binding: ActivityUpdateBinding
    private val api by lazy { EftvApi(deviceId = DeviceIdentity(this).id) }

    private var update: EftvApi.AppVersionInfo? = null
    private var downloadedFile: File? = null
    private var checking = false
    private var downloading = false
    private var waitingPermission = false
    /** Veio do aviso automatico: baixa sem pedir outro toque. */
    private var autoDownload = false

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityUpdateBinding.inflate(layoutInflater)
        setContentView(binding.root)

        setSupportActionBar(binding.toolbar)
        supportActionBar?.title = getString(R.string.update_title)
        supportActionBar?.setDisplayHomeAsUpEnabled(true)
        binding.toolbar.setNavigationOnClickListener { finish() }

        autoDownload = intent.getBooleanExtra(EXTRA_START_DOWNLOAD, false)
        binding.currentVersion.text =
            getString(R.string.update_current_version, BuildConfig.VERSION_NAME)
        binding.primaryButton.setOnClickListener { onPrimaryAction() }
        binding.secondaryButton.setOnClickListener { openInstallPermission() }

        // Consulta sempre ao abrir (inclusive se a tela for recriada): o
        // resultado e barato e evita guardar objeto de rede no estado.
        checkForUpdates()
    }

    override fun onResume() {
        super.onResume()
        TvScreen.apply(this)
        // Voltou do painel de permissao: se liberou, segue com o download sem
        // o cliente precisar tocar em nada de novo.
        if (waitingPermission && UpdateInstaller.canInstall(this)) {
            waitingPermission = false
            binding.secondaryButton.visibility = View.GONE
            update?.let { startDownload(it) }
        }
    }

    private fun onPrimaryAction() {
        if (checking || downloading) return

        downloadedFile?.let { file ->
            // Ja baixou e o cliente voltou sem concluir: reabre o instalador.
            UpdateInstaller.install(this, file)
            return
        }

        val info = update
        if (info != null && info.versionCode > BuildConfig.VERSION_CODE) {
            if (!UpdateInstaller.canInstall(this)) {
                askForInstallPermission()
            } else {
                startDownload(info)
            }
            return
        }

        checkForUpdates()
    }

    private fun checkForUpdates() {
        if (checking || downloading) return
        checking = true
        downloadedFile = null
        update = null
        binding.secondaryButton.visibility = View.GONE
        binding.notesText.visibility = View.GONE
        binding.progressBar.visibility = View.GONE
        setStatus(getString(R.string.update_checking))
        setPrimary(getString(R.string.update_check_again), enabled = false)

        lifecycleScope.launch {
            val result = runCatching { api.appVersion() }
            checking = false
            if (isFinishing || isDestroyed) return@launch

            result.onSuccess { info ->
                if (!info.configured || info.apkUrl.isBlank() ||
                    info.versionCode <= BuildConfig.VERSION_CODE
                ) {
                    showUpToDate()
                    return@onSuccess
                }
                if (!LogUtils.isSafeUpdateUrl(info.apkUrl)) {
                    Timber.w(
                        "Atualizacao ignorada: URL nao segura (%s)",
                        LogUtils.redactUrl(info.apkUrl),
                    )
                    showError(getString(R.string.update_invalid_source))
                    return@onSuccess
                }

                update = info
                setStatus(getString(R.string.update_available_new, info.versionName))
                setPrimary(getString(R.string.update_now), enabled = true)
                if (info.notes.isNotBlank()) {
                    binding.notesText.text = info.notes
                    binding.notesText.visibility = View.VISIBLE
                }
                if (autoDownload) {
                    autoDownload = false
                    if (UpdateInstaller.canInstall(this@UpdateActivity)) {
                        startDownload(info)
                    } else {
                        askForInstallPermission()
                    }
                }
            }.onFailure { error ->
                Timber.w(error, "Falha ao consultar a versao do app")
                showError(getString(R.string.update_check_failed))
            }
        }
    }

    private fun showUpToDate() {
        autoDownload = false
        setStatus(getString(R.string.update_up_to_date))
        setPrimary(getString(R.string.update_check_again), enabled = true)
    }

    private fun showError(message: String) {
        setStatus(message)
        setPrimary(getString(R.string.retry), enabled = true)
    }

    private fun askForInstallPermission() {
        waitingPermission = true
        setStatus(getString(R.string.update_permission_explain))
        binding.secondaryButton.visibility = View.VISIBLE
        openInstallPermission()
    }

    private fun openInstallPermission() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        val intent = Intent(
            Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,
            Uri.parse("package:$packageName"),
        )
        runCatching { startActivity(intent) }
            .onFailure {
                Timber.w(it, "Nao foi possivel abrir a tela de instalacao")
                setStatus(getString(R.string.update_permission_manual))
            }
    }

    private fun startDownload(info: EftvApi.AppVersionInfo) {
        if (downloading) return
        downloading = true
        waitingPermission = false
        binding.secondaryButton.visibility = View.GONE
        binding.progressBar.visibility = View.VISIBLE
        binding.progressBar.progress = 0
        setStatus(getString(R.string.update_downloading_unknown))
        setPrimary(getString(R.string.update_downloading_title), enabled = false)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)

        lifecycleScope.launch {
            try {
                val file = UpdateInstaller.download(this@UpdateActivity, info.apkUrl) { percent ->
                    runOnUiThread {
                        if (isFinishing || isDestroyed) return@runOnUiThread
                        if (percent < 0) {
                            binding.progressBar.isIndeterminate = true
                            setStatus(getString(R.string.update_downloading_unknown))
                        } else {
                            binding.progressBar.isIndeterminate = false
                            binding.progressBar.progress = percent
                            setStatus(getString(R.string.update_downloading_percent, percent))
                        }
                    }
                }

                if (!UpdateInstaller.isExpectedApk(this@UpdateActivity, file, info.versionCode)) {
                    file.delete()
                    throw IllegalStateException("APK baixado nao corresponde ao EFTV esperado")
                }

                downloadedFile = file
                binding.progressBar.isIndeterminate = false
                binding.progressBar.progress = 100
                binding.progressBar.visibility = View.GONE
                setStatus(getString(R.string.update_download_done))
                setPrimary(getString(R.string.update_install_again), enabled = true)
                UpdateInstaller.install(this@UpdateActivity, file)
                setStatus(getString(R.string.update_install_opened))
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                Timber.w(e, "Falha ao baixar a atualizacao")
                binding.progressBar.visibility = View.GONE
                showError(getString(R.string.update_download_failed))
            } finally {
                downloading = false
                window.clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
            }
        }
    }

    private fun setStatus(text: String) {
        binding.statusText.text = text
    }

    private fun setPrimary(text: String, enabled: Boolean) {
        binding.primaryButton.text = text
        binding.primaryButton.isEnabled = enabled
    }

    companion object {
        /** Quando true, o download comeca assim que a nova versao e encontrada. */
        const val EXTRA_START_DOWNLOAD = "start_download"
    }
}
