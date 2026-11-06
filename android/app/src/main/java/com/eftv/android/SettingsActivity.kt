package com.eftv.android

import android.content.Context
import android.content.SharedPreferences
import android.os.Bundle
import androidx.appcompat.app.AppCompatActivity
import androidx.preference.PreferenceFragmentCompat
import com.eftv.android.databinding.ActivitySettingsBinding

/**
 * Tela de configuracoes do app.
 *
 * A opcao de conteudo adulto fica DESLIGADA por padrao.
 * Acessivel pelo menu (⋮ -> Configuracoes) e pelo toque longo no titulo.
 */
class SettingsActivity : AppCompatActivity() {

    private lateinit var binding: ActivitySettingsBinding

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

    class SettingsFragment : PreferenceFragmentCompat() {
        override fun onCreatePreferences(savedInstanceState: Bundle?, rootKey: String?) {
            // Usa o mesmo arquivo lido por isAdultContentEnabled().
            preferenceManager.sharedPreferencesName = SettingsActivity.PREFS_NAME
            setPreferencesFromResource(R.xml.preferences, rootKey)

            findPreference<androidx.preference.Preference>("pref_version")?.summary =
                BuildConfig.VERSION_NAME
        }
    }

    companion object {
        /** Chave da preferencia de conteudo adulto. */
        const val PREF_SHOW_ADULT = "pref_show_adult"
        const val PREFS_NAME = "eftv_settings"

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
