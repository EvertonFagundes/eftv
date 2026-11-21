package com.eftv.android

import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import androidx.preference.ListPreference
import androidx.preference.Preference
import androidx.preference.PreferenceFragmentCompat
import androidx.preference.SwitchPreferenceCompat
import com.eftv.android.data.CatalogStore
import com.eftv.android.data.DeviceIdentity
import com.eftv.android.data.SessionStore
import com.eftv.android.data.api.EftvApi
import com.eftv.android.databinding.ActivitySettingsBinding
import com.google.android.material.dialog.MaterialAlertDialogBuilder
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import timber.log.Timber

/**
 * Tela de configuracoes do app.
 *
 * A opcao de conteudo adulto fica DESLIGADA por padrao.
 * Acessivel pelo menu (⋮ -> Configuracoes) e pelo toque longo no titulo.
 */
class SettingsActivity : AppCompatActivity() {

    private lateinit var binding: ActivitySettingsBinding
    private val session by lazy { SessionStore(this) }
    private val api by lazy { EftvApi(deviceId = DeviceIdentity(this).id) }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivitySettingsBinding.inflate(layoutInflater)
        setContentView(binding.root)

        setSupportActionBar(binding.toolbar)
        supportActionBar?.title = getString(R.string.settings_title)
        supportActionBar?.setDisplayHomeAsUpEnabled(true)

        binding.toolbar.setNavigationOnClickListener { onBackPressed() }

        supportFragmentManager.beginTransaction()
            .replace(R.id.settings_container, SettingsFragment())
            .commit()
    }

    override fun onResume() {
        super.onResume()
        TvScreen.apply(this)
    }

    /** Confirmacao antes de apagar a conta (acao irreversivel). */
    fun confirmDeleteAccount() {
        if (session.accessToken().isNullOrBlank()) {
            Toast.makeText(this, R.string.settings_delete_account_login, Toast.LENGTH_LONG).show()
            return
        }
        MaterialAlertDialogBuilder(this)
            .setTitle(R.string.settings_delete_account_title)
            .setMessage(R.string.settings_delete_account_message)
            .setNegativeButton(android.R.string.cancel, null)
            .setPositiveButton(R.string.settings_delete_account_confirm) { _, _ ->
                deleteAccount()
            }
            .show()
    }

    private fun deleteAccount() {
        val token = session.accessToken()
        if (token.isNullOrBlank()) {
            Toast.makeText(this, R.string.settings_delete_account_login, Toast.LENGTH_LONG).show()
            return
        }
        lifecycleScope.launch {
            try {
                api.deleteAccount(token)
                session.clear()
                Toast.makeText(
                    this@SettingsActivity,
                    R.string.settings_delete_account_done,
                    Toast.LENGTH_LONG,
                ).show()
                startActivity(
                    Intent(this@SettingsActivity, LoginActivity::class.java).apply {
                        addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK)
                    }
                )
                finish()
            } catch (e: EftvApi.ApiException) {
                Toast.makeText(this@SettingsActivity, e.detail, Toast.LENGTH_LONG).show()
            } catch (e: Exception) {
                Timber.w(e, "Falha ao excluir a conta")
                Toast.makeText(
                    this@SettingsActivity,
                    R.string.settings_delete_account_error,
                    Toast.LENGTH_LONG,
                ).show()
            }
        }
    }

    class SettingsFragment : PreferenceFragmentCompat() {
        override fun onCreatePreferences(savedInstanceState: Bundle?, rootKey: String?) {
            setPreferencesFromResource(R.xml.preferences, rootKey)

            findPreference<Preference>("pref_version")?.summary = BuildConfig.VERSION_NAME

            // Exclusao de conta (Play Store / LGPD).
            findPreference<Preference>("pref_delete_account")?.setOnPreferenceClickListener {
                (activity as? SettingsActivity)?.confirmDeleteAccount()
                true
            }

            // Margem de seguranca da TV: so faz sentido (e so aparece) em
            // Android TV / TV box. O valor real fica em TvScreen.
            val tvCategory = findPreference<Preference>("category_tv")
            if (!TvScreen.isTelevision(requireContext())) {
                tvCategory?.isVisible = false
            } else {
                findPreference<ListPreference>(TvScreen.PREF_OVERSCAN_DP)?.apply {
                    isPersistent = false
                    value = TvScreen.overscanDp(requireContext()).toString()
                    setOnPreferenceChangeListener { _, newValue ->
                        val dp = (newValue as? String)?.toIntOrNull()
                            ?: TvScreen.DEFAULT_OVERSCAN_DP
                        TvScreen.setOverscanDp(requireContext(), dp)
                        true
                    }
                }
            }

            // Termos e politica: paginas publicadas no site oficial.
            findPreference<Preference>("pref_terms")?.setOnPreferenceClickListener {
                openUrl(SettingsActivity.URL_TERMOS)
                true
            }
            findPreference<Preference>("pref_privacy")?.setOnPreferenceClickListener {
                openUrl(SettingsActivity.URL_PRIVACIDADE)
                true
            }

            // O switch nao grava sozinho: a fonte da verdade e o arquivo que o
            // app le em isAdultContentEnabled(). Antes o PreferenceManager podia
            // usar outro arquivo e a opcao nunca tinha efeito no catalogo.
            findPreference<SwitchPreferenceCompat>(SettingsActivity.PREF_SHOW_ADULT)?.apply {
                isPersistent = false
                isChecked = SettingsActivity.isAdultContentEnabled(requireContext())
                setOnPreferenceChangeListener { _, novoValor ->
                    SettingsActivity.setAdultContentEnabled(
                        requireContext(),
                        novoValor == true,
                    )
                    true
                }
            }

            // A opcao so aparece quando a playlist traz algum grupo adulto;
            // sem conteudo ela so geraria duvida no cliente.
            hideAdultOptionIfEmpty()
        }

        /** Abre uma pagina oficial no navegador. */
        private fun openUrl(url: String) {
            runCatching {
                startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url)))
            }
        }

        private fun hideAdultOptionIfEmpty() {
            val adultPref = findPreference<Preference>(SettingsActivity.PREF_SHOW_ADULT) ?: return
            val category = findPreference<Preference>(SettingsActivity.CATEGORY_PRIVACY) ?: return
            lifecycleScope.launch {
                val hasAdult = withContext(Dispatchers.IO) {
                    runCatching {
                        CatalogStore.get(requireContext()).hasAdultGroup()
                    }.getOrDefault(false)
                }
                if (!hasAdult && isAdded) {
                    adultPref.isVisible = false
                    category.isVisible = false
                }
            }
        }
    }

    companion object {
        /** Chave da preferencia de conteudo adulto. */
        const val PREF_SHOW_ADULT = "pref_show_adult"
        const val PREFS_NAME = "eftv_settings"

        /** Chave da categoria que guarda a opcao de conteudo adulto. */
        private const val CATEGORY_PRIVACY = "category_privacy"

        /** Paginas legais publicadas no site oficial. */
        const val URL_TERMOS =
            "https://evertonfagundes.github.io/eftv/termos.html"
        const val URL_PRIVACIDADE =
            "https://evertonfagundes.github.io/eftv/privacidade.html"

        /** Verifica se o conteudo adulto esta liberado. */
        @JvmStatic
        fun isAdultContentEnabled(context: Context): Boolean {
            val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            return prefs.getBoolean(PREF_SHOW_ADULT, false)
        }

        /** Define se o conteudo adulto esta liberado. */
        @JvmStatic
        fun setAdultContentEnabled(context: Context, enabled: Boolean) {
            val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            prefs.edit().putBoolean(PREF_SHOW_ADULT, enabled).apply()
        }
    }
}
