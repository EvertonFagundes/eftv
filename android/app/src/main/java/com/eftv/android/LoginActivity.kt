package com.eftv.android

import android.content.Intent
import android.os.Bundle
import android.view.View
import android.view.inputmethod.EditorInfo
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import com.eftv.android.data.SessionStore
import com.eftv.android.data.api.EftvApi
import com.eftv.android.databinding.ActivityLoginBinding
import kotlinx.coroutines.launch
import timber.log.Timber

/**
 * Entrada do assinante. Sem login o app continua abrindo a lista local
 * (modo demonstracao), para nunca ficar inutilizavel.
 */
class LoginActivity : AppCompatActivity() {

    private lateinit var binding: ActivityLoginBinding
    private val session by lazy { SessionStore(this) }
    private val api by lazy { EftvApi() }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityLoginBinding.inflate(layoutInflater)
        setContentView(binding.root)

        binding.versionText.text = getString(
            R.string.login_version,
            BuildConfig.VERSION_NAME,
            BuildConfig.API_BASE_URL,
        )

        if (session.hasSession()) {
            openCatalog()
            return
        }

        binding.loginButton.setOnClickListener { signIn() }
        binding.offlineButton.setOnClickListener {
            openCatalog(skipAuth = true)
        }
        binding.passwordInput.setOnEditorActionListener { _, actionId, _ ->
            if (actionId == EditorInfo.IME_ACTION_DONE) {
                signIn()
                true
            } else {
                false
            }
        }
    }

    private fun signIn() {
        val email = binding.emailInput.text?.toString().orEmpty().trim()
        val password = binding.passwordInput.text?.toString().orEmpty()

        if (email.isBlank() || password.isBlank()) {
            showError(getString(R.string.login_fill_fields))
            return
        }

        setLoading(true)
        lifecycleScope.launch {
            try {
                val tokens = api.login(email, password)
                session.save(tokens, email)
                openCatalog()
            } catch (e: EftvApi.ApiException) {
                setLoading(false)
                showError(messageFor(e))
            } catch (e: Exception) {
                setLoading(false)
                showError(getString(R.string.login_network_error))
                Timber.e(e, "Falha ao entrar")
            }
        }
    }

    private fun messageFor(e: EftvApi.ApiException): String = when (e.statusCode) {
        401 -> getString(R.string.login_invalid_credentials)
        403 -> getString(R.string.login_user_disabled)
        else -> e.detail
    }

    private fun openCatalog(skipAuth: Boolean = false) {
        startActivity(
            Intent(this, MainActivity::class.java).apply {
                putExtra(MainActivity.EXTRA_SKIP_AUTH, skipAuth)
            }
        )
        finish()
    }

    private fun setLoading(loading: Boolean) {
        binding.loginButton.isEnabled = !loading
        binding.offlineButton.isEnabled = !loading
        binding.emailInput.isEnabled = !loading
        binding.passwordInput.isEnabled = !loading
        binding.loginProgress.visibility = if (loading) View.VISIBLE else View.GONE
        if (loading) binding.loginError.visibility = View.GONE
    }

    private fun showError(message: String) {
        binding.loginError.text = message
        binding.loginError.visibility = View.VISIBLE
    }
}
