package com.eftv.android

import android.content.Intent
import android.os.Build
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
 * Entrada do assinante.
 *
 * Fluxo:
 * 1. Sem sessão: mostra tela de login/cadastro.
 * 2. Após login ou cadastro bem-sucedido:
 *    - Se email já verificado → abre o catálogo.
 *    - Se email NÃO verificado → abre EmailVerificationActivity (7 dias grátis só após confirmação).
 * 3. Modo local (sem backend): abre direto no catálogo (demonstração).
 */
class LoginActivity : AppCompatActivity() {

    private lateinit var binding: ActivityLoginBinding
    private val session by lazy { SessionStore(this) }
    private val api by lazy { EftvApi() }

    // Modo cadastro ativado/desativado
    private var isRegisterMode = false

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityLoginBinding.inflate(layoutInflater)
        setContentView(binding.root)
        requestNotificationPermission()

        binding.versionText.text = getString(
            R.string.login_version,
            BuildConfig.VERSION_NAME,
            BuildConfig.API_BASE_URL,
        )

        // No modo local o servidor embutido e a fonte do catalogo: nao ha
        // login nem backend para esperar.
        if (BuildConfig.LOCAL_MODE) {
            openCatalog(skipAuth = true)
            return
        }

        // Já tem sessão válida?
        if (session.hasSession()) {
            if (session.isEmailVerified()) {
                openCatalog()
            } else {
                openEmailVerification()
            }
            return
        }

        binding.loginButton.setOnClickListener { signInOrRegister() }
        binding.registerButton.setOnClickListener { toggleRegisterMode() }
        binding.passwordInput.setOnEditorActionListener { _, actionId, _ ->
            if (actionId == EditorInfo.IME_ACTION_DONE) {
                signInOrRegister()
                true
            } else {
                false
            }
        }
        binding.fullNameInput.setOnEditorActionListener { _, actionId, _ ->
            if (actionId == EditorInfo.IME_ACTION_DONE) {
                signInOrRegister()
                true
            } else {
                false
            }
        }

        updateAuthModeUI()
    }

    private fun toggleRegisterMode() {
        isRegisterMode = !isRegisterMode
        updateAuthModeUI()
    }

    private fun updateAuthModeUI() {
        if (isRegisterMode) {
            binding.registerButton.text = getString(R.string.register_already_have_account)
            binding.loginButton.text = getString(R.string.register_create_account)
            binding.fullNameLayout.visibility = View.VISIBLE
            binding.passwordInput.imeOptions = EditorInfo.IME_ACTION_NEXT
        } else {
            binding.registerButton.text = getString(R.string.register_create_account)
            binding.loginButton.text = getString(R.string.login_enter)
            binding.fullNameLayout.visibility = View.GONE
            binding.passwordInput.imeOptions = EditorInfo.IME_ACTION_DONE
        }
    }

    private fun signInOrRegister() {
        val email = binding.emailInput.text?.toString().orEmpty().trim()
        val password = binding.passwordInput.text?.toString().orEmpty()
        val fullName = binding.fullNameInput.text?.toString().orEmpty().trim()

        if (email.isBlank() || password.isBlank()) {
            showError(getString(R.string.login_fill_fields))
            return
        }

        if (isRegisterMode && password.length < 8) {
            showError(getString(R.string.register_password_too_short))
            return
        }

        setLoading(true)
        binding.loginError.visibility = View.GONE
        lifecycleScope.launch {
            try {
                if (isRegisterMode) {
                    val tokens = api.register(email, password, fullName.takeIf { it.isNotBlank() })
                    session.save(tokens, email, emailVerified = false)
                } else {
                    val tokens = api.login(email, password)
                    // A flag local pode estar desatualizada (conta verificada
                    // em outro aparelho/site), entao consultamos o servidor.
                    val verified = try {
                        api.me(tokens.accessToken).emailVerified
                    } catch (_: Exception) {
                        session.isEmailVerified()
                    }
                    session.save(tokens, email, emailVerified = verified)
                }

                // Redireciona conforme status de verificação
                if (session.isEmailVerified()) {
                    openCatalog()
                } else {
                    openEmailVerification()
                }
            } catch (e: EftvApi.ApiException) {
                setLoading(false)
                showError(messageFor(e))
            } catch (e: Exception) {
                setLoading(false)
                showError(
                    if (BuildConfig.DEBUG) {
                        getString(R.string.login_network_error_debug, BuildConfig.API_BASE_URL)
                    } else {
                        getString(R.string.login_network_error)
                    }
                )
                Timber.e(e, "Falha ao autenticar em %s", BuildConfig.API_BASE_URL)
            }
        }
    }

    private fun messageFor(e: EftvApi.ApiException): String = when (e.statusCode) {
        400 -> e.detail.ifEmpty { getString(R.string.register_email_exists) }
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

    private fun openEmailVerification() {
        val email = session.email().orEmpty()
        startActivity(
            Intent(this, EmailVerificationActivity::class.java).apply {
                putExtra(EmailVerificationActivity.EXTRA_EMAIL, email)
            }
        )
        finish()
    }

    private fun setLoading(loading: Boolean) {
        binding.loginButton.isEnabled = !loading
        binding.registerButton.isEnabled = !loading
        binding.emailInput.isEnabled = !loading
        binding.passwordInput.isEnabled = !loading
        binding.fullNameInput.isEnabled = !loading
        binding.loginProgress.visibility = if (loading) View.VISIBLE else View.GONE
        if (loading) binding.loginError.visibility = View.GONE
    }

    private fun requestNotificationPermission() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU) return
        if (checkSelfPermission(android.Manifest.permission.POST_NOTIFICATIONS) ==
            android.content.pm.PackageManager.PERMISSION_GRANTED
        ) return
        requestPermissions(arrayOf(android.Manifest.permission.POST_NOTIFICATIONS), 8124)
    }

    private fun showError(message: String) {
        binding.loginError.text = message
        binding.loginError.visibility = View.VISIBLE
    }
}
