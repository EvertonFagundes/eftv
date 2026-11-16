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
        binding.switchAccountButton.setOnClickListener {
            // Sai da conta atual e volta ao login (evita ficar preso na tela).
            session.clear()
            startActivity(Intent(this, LoginActivity::class.java))
            finish()
        }

        // Se a conta ja foi verificada no servidor (outro aparelho/site), nao
        // deixa o usuario preso nesta tela.
        lifecycleScope.launch { checkIfAlreadyVerified() }
        binding.tokenInput.setOnEditorActionListener { _, actionId, _ ->
            if (actionId == EditorInfo.IME_ACTION_DONE) {
                verifyEmail()
                true
            } else {
                false
            }
        }
    }

    override fun onResume() {
        super.onResume()
        // O e-mail manda um LINK. O usuario confirma no navegador e volta para
        // o app: aqui a verificacao e detectada sem pedir codigo.
        lifecycleScope.launch { checkIfAlreadyVerified() }
    }

    private fun verifyEmail() {
        val raw = binding.tokenInput.text?.toString().orEmpty().trim()

        // Aceita o link inteiro (o usuario costuma colar o link do e-mail).
        val token = when {
            raw.isBlank() -> ""
            raw.startsWith("http") -> Uri.parse(raw).getQueryParameter("token").orEmpty()
            else -> raw
        }

        if (token.isBlank()) {
            // Sem codigo: confere se ele ja confirmou pelo link.
            setLoading(true)
            binding.error.visibility = View.GONE
            lifecycleScope.launch {
                if (!checkIfAlreadyVerified(feedback = true)) {
                    setLoading(false)
                }
            }
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
                api.resendVerification(email)
                setLoading(false)
                binding.error.text = getString(R.string.verify_resent)
                binding.error.visibility = View.VISIBLE
                binding.error.setTextColor(
                    androidx.core.content.ContextCompat.getColor(
                        this@EmailVerificationActivity, R.color.primary,
                    )
                )
            } catch (e: Exception) {
                setLoading(false)
                showError(getString(R.string.verify_network_error))
                Timber.e(e, "Falha ao reenhar verificacao")
            }
        }
    }

    /**
     * Consulta o servidor para saber se o email ja esta verificado. Se estiver,
     * libera o catalogo imediatamente.
     *
     * @return true se a conta ja esta verificada.
     */
    private suspend fun checkIfAlreadyVerified(feedback: Boolean = false): Boolean {
        val accessToken = session.accessToken()
        if (accessToken.isNullOrBlank()) return false
        return try {
            if (api.me(accessToken).emailVerified) {
                session.setEmailVerified(true)
                openCatalog()
                true
            } else {
                if (feedback) showError(getString(R.string.verify_not_confirmed))
                false
            }
        } catch (e: Exception) {
            // Sem rede ou token expirado: o usuario continua na tela.
            if (feedback) showError(getString(R.string.verify_network_error))
            false
        }
    }

    private fun openVerificationLinkInBrowser() {
        val email = session.email().orEmpty()
        // O e-mail de confirmacao chega na caixa de entrada; abrir o app de
        // e-mail e o caminho mais direto para o link.
        val intent = Intent(Intent.ACTION_VIEW).apply {
            data = Uri.parse("mailto:$email")
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
        binding.switchAccountButton.isEnabled = !loading
        binding.tokenInput.isEnabled = !loading
        binding.verifyProgress.visibility = if (loading) View.VISIBLE else View.GONE
    }

    private fun showError(message: String) {
        binding.error.text = message
        binding.error.visibility = View.VISIBLE
    }
}
