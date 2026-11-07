package com.eftv.android

import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.view.View
import android.view.inputmethod.EditorInfo
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import com.eftv.android.data.SessionStore
import com.eftv.android.data.api.EftvApi
import com.eftv.android.databinding.ActivityEmailVerificationBinding
import kotlinx.coroutines.launch
import timber.log.Timber

/**
 * Tela de verificacao de email.
 *
 * O usuario recebeu um token por email apos se cadastrar. Aqui ele pode:
 * - Digitar o token (ou clicar no link do email que abre esta mesma tela com ?token=...)
 * - Clicar em "Abrir link no navegador" para verificar via navegador
 * - Solicitar reenvio do email de verificacao
 *
 * Apos a verificacao bem-sucedida, o trial gratuito de 7 dias e ativado no
 * backend e o usuario e direcionado para o catalogo.
 */
class EmailVerificationActivity : AppCompatActivity() {

    companion object {
        const val EXTRA_EMAIL = "extra_email"
    }

    private lateinit var binding: ActivityEmailVerificationBinding
    private val session by lazy { SessionStore(this) }
    private val api by lazy { EftvApi() }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityEmailVerificationBinding.inflate(layoutInflater)
        setContentView(binding.root)

        val email = intent.getStringExtra(EXTRA_EMAIL) ?: session.email().orEmpty()
        binding.emailDisplay.text = getString(R.string.verify_email_for, email)

        // Se vier token via intent (deep link do email), preenche automaticamente
        val token = intent.data?.getQueryParameter("token")
        if (token != null) {
            binding.tokenInput.setText(token)
        }

        binding.verifyButton.setOnClickListener { verifyEmail() }
        binding.resendButton.setOnClickListener { resendVerification() }
        binding.openBrowserButton.setOnClickListener { openVerificationLinkInBrowser() }
        binding.tokenInput.setOnEditorActionListener { _, actionId, _ ->
            if (actionId == EditorInfo.IME_ACTION_DONE) {
                verifyEmail()
                true
            } else {
                false
            }
        }
    }

    private fun verifyEmail() {
        val token = binding.tokenInput.text?.toString().orEmpty().trim()
        if (token.isBlank()) {
            binding.error.text = getString(R.string.verify_enter_token)
            binding.error.visibility = View.VISIBLE
            return
        }

        setLoading(true)
        binding.error.visibility = View.GONE
        lifecycleScope.launch {
            try {
                val result = api.verifyEmail(token)
                if (result.emailVerified) {
                    // Atualiza sessão local (apenas a flag de email verificado)
                    session.setEmailVerified(true)
                    openCatalog()
                } else {
                    setLoading(false)
                    showError(result.message.ifEmpty { getString(R.string.verify_failed) })
                }
            } catch (e: EftvApi.ApiException) {
                setLoading(false)
                showError(when (e.statusCode) {
                    400 -> getString(R.string.verify_invalid_or_expired_token)
                    else -> e.detail
                })
            } catch (e: Exception) {
                setLoading(false)
                showError(getString(R.string.verify_network_error))
                Timber.e(e, "Falha ao verificar email")
            }
        }
    }

    private fun resendVerification() {
        val email = session.email().orEmpty()
        if (email.isBlank()) {
            showError(getString(R.string.verify_no_email))
            return
        }

        setLoading(true)
        binding.error.visibility = View.GONE
        lifecycleScope.launch {
            try {
                val message = api.resendVerification(email)
                setLoading(false)
                binding.error.text = getString(R.string.verify_resent, message)
                binding.error.visibility = View.VISIBLE
                binding.error.setTextColor(
                    androidx.core.content.ContextCompat.getColor(this, R.color.primary)
                )
            } catch (e: Exception) {
                setLoading(false)
                showError(getString(R.string.verify_network_error))
                Timber.e(e, "Falha ao reenhar verificacao")
            }
        }
    }

    private fun openVerificationLinkInBrowser() {
        val email = session.email().orEmpty()
        // Instrui o usuario a verificar o email e clicar no link, que abre este app via deep link
        val subject = "Confirme seu email - EFTV"
        val body = "Acesse seu email e clique no link de confirmacao enviado pelo EFTV."
        val intent = Intent(Intent.ACTION_VIEW).apply {
            data = Uri.parse("mailto:$email?subject=$subject&body=$body")
        }
        if (intent.resolveActivity(packageManager) != null) {
            startActivity(intent)
        }
    }

    private fun openCatalog() {
        startActivity(Intent(this, MainActivity::class.java))
        finish()
    }

    private fun setLoading(loading: Boolean) {
        binding.verifyButton.isEnabled = !loading
        binding.resendButton.isEnabled = !loading
        binding.openBrowserButton.isEnabled = !loading
        binding.tokenInput.isEnabled = !loading
        binding.verifyProgress.visibility = if (loading) View.VISIBLE else View.GONE
    }

    private fun showError(message: String) {
        binding.error.text = message
        binding.error.visibility = View.VISIBLE
    }
}
