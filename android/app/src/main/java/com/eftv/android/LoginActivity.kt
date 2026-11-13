package com.eftv.android

import android.content.Intent
import android.os.Build
import android.os.Bundle
import android.view.View
import android.view.inputmethod.EditorInfo
import android.widget.Toast
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import com.eftv.android.data.SessionStore
import com.eftv.android.data.api.EftvApi
import com.eftv.android.databinding.ActivityLoginBinding
import com.eftv.android.databinding.DialogPasswordResetBinding
import com.google.android.material.dialog.MaterialAlertDialogBuilder
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
        binding.forgotPassword.setOnClickListener { showForgotPasswordDialog() }
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
            binding.forgotPassword.visibility = View.GONE
        } else {
            binding.registerButton.text = getString(R.string.register_create_account)
            binding.loginButton.text = getString(R.string.login_enter)
            binding.fullNameLayout.visibility = View.GONE
            binding.passwordInput.imeOptions = EditorInfo.IME_ACTION_DONE
            binding.forgotPassword.visibility = View.VISIBLE
        }
    }

    /**
     * Recuperacao de senha: envia um codigo de 6 digitos para o email da
     * conta e permite cadastrar uma nova senha. Funciona para qualquer
     * usuario do app, sem depender de suporte manual.
     */
    private fun showForgotPasswordDialog() {
        val dialogBinding = DialogPasswordResetBinding.inflate(layoutInflater)
        dialogBinding.resetEmailInput.setText(binding.emailInput.text?.toString().orEmpty().trim())

        val dialog = MaterialAlertDialogBuilder(this)
            .setTitle(R.string.forgot_password_title)
            .setView(dialogBinding.root)
            .setPositiveButton(R.string.forgot_password_confirm, null)
            .setNegativeButton(R.string.forgot_password_cancel, null)
            .create()

        dialog.setOnShowListener {
            dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener {
                submitPasswordReset(dialogBinding, dialog)
            }
        }

        dialogBinding.resetSendCodeButton.setOnClickListener { button ->
            val email = dialogBinding.resetEmailInput.text?.toString().orEmpty().trim()
            if (email.isBlank()) {
                setResetStatus(dialogBinding, getString(R.string.login_fill_fields), isError = true)
                return@setOnClickListener
            }
            button.isEnabled = false
            setResetStatus(dialogBinding, getString(R.string.forgot_password_sending), isError = false)
            lifecycleScope.launch {
                try {
                    api.forgotPassword(email)
                    setResetStatus(
                        dialogBinding,
                        getString(R.string.forgot_password_code_sent),
                        isError = false,
                    )
                } catch (e: Exception) {
                    Timber.e(e, "Falha ao pedir codigo de recuperacao")
                    setResetStatus(
                        dialogBinding,
                        getString(R.string.forgot_password_network),
                        isError = true,
                    )
                } finally {
                    button.isEnabled = true
                }
            }
        }

        dialog.show()
    }

    private fun submitPasswordReset(
        dialogBinding: DialogPasswordResetBinding,
        dialog: AlertDialog,
    ) {
        val email = dialogBinding.resetEmailInput.text?.toString().orEmpty().trim()
        val code = dialogBinding.resetCodeInput.text?.toString().orEmpty().trim()
        val newPassword = dialogBinding.resetPasswordInput.text?.toString().orEmpty()

        if (email.isBlank() || code.isBlank() || newPassword.isBlank()) {
            setResetStatus(dialogBinding, getString(R.string.forgot_password_fill_fields), isError = true)
            return
        }
        if (newPassword.length < 8) {
            setResetStatus(dialogBinding, getString(R.string.forgot_password_short), isError = true)
            return
        }

        setResetStatus(dialogBinding, getString(R.string.forgot_password_sending), isError = false)
        lifecycleScope.launch {
            try {
                api.resetPassword(email, code, newPassword)
                dialog.dismiss()
                binding.emailInput.setText(email)
                binding.passwordInput.setText("")
                Toast.makeText(
                    this@LoginActivity,
                    R.string.forgot_password_success,
                    Toast.LENGTH_LONG,
                ).show()
            } catch (e: EftvApi.ApiException) {
                setResetStatus(
                    dialogBinding,
                    e.detail.ifBlank { getString(R.string.forgot_password_network) },
                    isError = true,
                )
            } catch (e: Exception) {
                Timber.e(e, "Falha ao redefinir senha")
                setResetStatus(
                    dialogBinding,
                    getString(R.string.forgot_password_network),
                    isError = true,
                )
            }
        }
    }

    private fun setResetStatus(
        dialogBinding: DialogPasswordResetBinding,
        message: String,
        isError: Boolean,
    ) {
        dialogBinding.resetStatus.text = message
        dialogBinding.resetStatus.setTextColor(
            androidx.core.content.ContextCompat.getColor(
                this,
                if (isError) R.color.error else R.color.on_surface_variant,
            )
        )
        dialogBinding.resetStatus.visibility = View.VISIBLE
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
