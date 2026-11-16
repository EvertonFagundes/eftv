package com.eftv.android

import android.content.ActivityNotFoundException
import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.view.View
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import com.eftv.android.data.DeviceIdentity
import com.eftv.android.data.SessionStore
import com.eftv.android.data.api.EftvApi
import com.eftv.android.databinding.ActivitySubscriptionBinding
import com.google.android.material.dialog.MaterialAlertDialogBuilder
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import timber.log.Timber
import java.text.DateFormat
import java.text.NumberFormat
import java.text.SimpleDateFormat
import java.util.Locale
import java.util.TimeZone

/**
 * Tela "Minha assinatura".
 *
 * Mostra o estado real da conta (teste gratis, ativa, pendente ou inativa),
 * o preco do plano, quantos aparelhos o plano libera e o botao para pagar no
 * Mercado Pago. Depois do pagamento o cliente volta para o app e atualiza o
 * status aqui mesmo, sem depender de suporte.
 */
class SubscriptionActivity : AppCompatActivity() {

    private lateinit var binding: ActivitySubscriptionBinding
    private val session by lazy { SessionStore(this) }
    private val device by lazy { DeviceIdentity(this) }
    private val api by lazy { EftvApi(deviceId = device.id, deviceName = device.name) }

    private var overview: EftvApi.SubscriptionOverview? = null

    /** Verdadeiro depois de abrir o checkout: ao voltar do navegador, atualiza. */
    private var awaitingPayment = false

    /** Primeira execucao do onResume nao deve recarregar (o onCreate ja fez). */
    private var started = false

    private val currencyFormat: NumberFormat by lazy {
        NumberFormat.getCurrencyInstance(Locale("pt", "BR"))
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivitySubscriptionBinding.inflate(layoutInflater)
        setContentView(binding.root)

        binding.toolbar.setNavigationOnClickListener { finish() }

        binding.subscribeButton.setOnClickListener { startCheckout() }
        binding.refreshButton.setOnClickListener { load(silent = false) }
        binding.devicesButton.setOnClickListener { showDevices() }
        binding.cancelButton.setOnClickListener { confirmCancel() }

        load(silent = false)
    }

    override fun onResume() {
        super.onResume()
        if (!started) {
            started = true
            return
        }
        // Voltou do navegador (ou de outra tela): revalida o pagamento.
        if (awaitingPayment) load(silent = true)
    }

    // ------------------------------------------------------------------
    // Carregamento
    // ------------------------------------------------------------------

    private fun load(silent: Boolean) {
        val token = session.accessToken()
        if (token.isNullOrBlank()) {
            finish()
            return
        }

        setLoading(!silent)
        lifecycleScope.launch {
            val result = try {
                fetchOverview(token)
            } catch (e: EftvApi.ApiException) {
                if (e.statusCode == 401) {
                    finish()
                } else {
                    showLoadError(e.detail)
                }
                null
            } catch (e: Exception) {
                Timber.w(e, "Falha ao carregar a assinatura")
                showLoadError(getString(R.string.subscription_load_error))
                null
            }

            setLoading(false)
            if (isFinishing) return@launch
            result?.let {
                overview = it
                render(it)
            }
        }
    }

    private suspend fun fetchOverview(token: String): EftvApi.SubscriptionOverview {
        return try {
            api.subscriptionOverview(token)
        } catch (e: EftvApi.ApiException) {
            if (e.statusCode != 401) throw e
            // Access token curto: renova e tenta de novo uma vez.
            val refreshToken = session.refreshToken()
            if (refreshToken.isNullOrBlank()) throw e
            val tokens = api.refresh(refreshToken)
            session.save(tokens, session.email().orEmpty(), session.isEmailVerified())
            api.subscriptionOverview(tokens.accessToken)
        }
    }

    // ------------------------------------------------------------------
    // Tela
    // ------------------------------------------------------------------

    private fun render(overview: EftvApi.SubscriptionOverview) {
        binding.priceText.text = currencyFormat.format(overview.priceCents / 100.0)
        binding.benefitsText.text = getString(
            R.string.subscription_benefits,
            overview.maxDevices,
            overview.maxStreams,
        )
        renderPayment(overview)

        val periodEnd = formatDate(overview.currentPeriodEnd)
        val trialEnd = formatDate(overview.trialEnd)
        val days = resources.getQuantityString(
            R.plurals.subscription_days_remaining,
            overview.daysRemaining,
            overview.daysRemaining,
        )

        when {
            overview.hasAccess && overview.status == "trial" -> {
                binding.statusTitle.text = getString(R.string.subscription_status_trial)
                binding.statusDetail.text = getString(
                    R.string.subscription_trial_detail,
                    days,
                    trialEnd ?: periodEnd.orEmpty(),
                )
                showSubscribe(true, R.string.subscription_subscribe_now)
            }

            overview.hasAccess -> {
                binding.statusTitle.text = getString(R.string.subscription_status_active)
                binding.statusDetail.text = if (overview.cancelAtPeriodEnd) {
                    getString(R.string.subscription_cancelled_detail, periodEnd.orEmpty())
                } else {
                    getString(
                        R.string.subscription_active_detail,
                        days,
                        periodEnd.orEmpty(),
                    )
                }
                showSubscribe(false, R.string.subscription_subscribe_now)
                binding.cancelButton.visibility =
                    if (overview.cancelAtPeriodEnd) View.GONE else View.VISIBLE
            }

            overview.status == "pending" -> {
                binding.statusTitle.text = getString(R.string.subscription_status_pending)
                binding.statusDetail.text = getString(R.string.subscription_pending_detail)
                showSubscribe(true, R.string.subscription_continue_payment)
            }

            else -> {
                binding.statusTitle.text = getString(R.string.subscription_status_inactive)
                binding.statusDetail.text = getString(R.string.subscription_inactive_detail)
                showSubscribe(true, R.string.subscription_subscribe_now)
            }
        }
    }

    /** Mostra o cartao/cobranca usada na ultima renovacao (quando o servidor sabe). */
    private fun renderPayment(overview: EftvApi.SubscriptionOverview) {
        val method = overview.paymentMethod
        val view = binding.paymentText
        when {
            method.isNullOrBlank() -> view.visibility = View.GONE

            else -> {
                val brand = paymentBrand(method)
                val lastFour = overview.paymentLastFour
                view.text = if (lastFour.isNullOrBlank()) {
                    getString(R.string.subscription_payment_method, brand)
                } else {
                    getString(R.string.subscription_payment_card, brand, lastFour)
                }
                view.visibility = View.VISIBLE
            }
        }
    }

    /** Siglas do Mercado Pago ("visa", "master"...) em nome legivel. */
    private fun paymentBrand(method: String): String = when (method.lowercase()) {
        "visa" -> "Visa"
        "master", "mastercard" -> "Mastercard"
        "elo" -> "Elo"
        "amex" -> "American Express"
        "hipercard" -> "Hipercard"
        "cabal" -> "Cabal"
        "naranja" -> "Naranja X"
        "pagoseguro" -> "PagoSeguro"
        "credipago" -> "Credipago"
        else -> method.replaceFirstChar { it.uppercase() }
    }

    private fun showSubscribe(visible: Boolean, labelRes: Int) {
        binding.subscribeButton.visibility = if (visible) View.VISIBLE else View.GONE
        binding.subscribeButton.setText(labelRes)
        binding.cancelButton.visibility = View.GONE
    }

    private fun setLoading(loading: Boolean) {
        binding.progress.visibility = if (loading) View.VISIBLE else View.GONE
        binding.subscribeButton.isEnabled = !loading
        binding.refreshButton.isEnabled = !loading
        binding.devicesButton.isEnabled = !loading
    }

    private fun showLoadError(message: String) {
        Toast.makeText(
            this,
            message.ifBlank { getString(R.string.subscription_load_error) },
            Toast.LENGTH_LONG,
        ).show()
    }

    // ------------------------------------------------------------------
    // Pagamento
    // ------------------------------------------------------------------

    private fun startCheckout() {
        val current = overview ?: return
        val token = session.accessToken()
        if (token.isNullOrBlank()) {
            finish()
            return
        }

        binding.subscribeButton.isEnabled = false
        binding.progress.visibility = View.VISIBLE
        lifecycleScope.launch {
            try {
                val checkout = withContext(Dispatchers.IO) {
                    api.createCheckout(token, current.planId)
                }
                openBrowser(checkout.initPoint)
                awaitingPayment = true
                MaterialAlertDialogBuilder(this@SubscriptionActivity)
                    .setTitle(R.string.subscription_checkout_title)
                    .setMessage(R.string.subscription_checkout_message)
                    .setPositiveButton(R.string.close, null)
                    .show()
            } catch (e: EftvApi.ApiException) {
                if (e.statusCode == 409) {
                    // Ja existe assinatura paga ativa: so atualiza a tela.
                    Toast.makeText(
                        this@SubscriptionActivity,
                        R.string.subscription_already_active,
                        Toast.LENGTH_LONG,
                    ).show()
                    load(silent = true)
                } else {
                    showLoadError(e.detail)
                }
            } catch (e: Exception) {
                Timber.w(e, "Falha ao criar o checkout")
                showLoadError(getString(R.string.subscription_checkout_error))
            } finally {
                binding.subscribeButton.isEnabled = true
                binding.progress.visibility = View.GONE
            }
        }
    }

    private fun openBrowser(url: String) {
        val intent = Intent(Intent.ACTION_VIEW, Uri.parse(url))
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        try {
            startActivity(intent)
        } catch (e: ActivityNotFoundException) {
            Timber.w(e, "Nenhum navegador instalado")
            Toast.makeText(this, R.string.subscription_checkout_error, Toast.LENGTH_LONG).show()
        }
    }

    // ------------------------------------------------------------------
    // Aparelhos
    // ------------------------------------------------------------------

    private fun showDevices() {
        val token = session.accessToken()
        if (token.isNullOrBlank()) {
            finish()
            return
        }

        lifecycleScope.launch {
            val access = try {
                withContext(Dispatchers.IO) { api.deviceAccess(token) }
            } catch (e: Exception) {
                Timber.w(e, "Falha ao consultar aparelhos")
                Toast.makeText(
                    this@SubscriptionActivity,
                    R.string.device_load_error,
                    Toast.LENGTH_LONG,
                ).show()
                return@launch
            }
            if (isFinishing) return@launch

            val message = buildString {
                append(getString(R.string.device_limit_info, access.bound, access.limit))
                if (access.devices.isNotEmpty()) {
                    append("\n")
                    access.devices.forEach { item ->
                        val name = item.deviceName ?: getString(R.string.device_unnamed)
                        append("\n• ")
                        append(name)
                        if (item.current) append(" (este aparelho)")
                    }
                }
            }

            val dialog = MaterialAlertDialogBuilder(this@SubscriptionActivity)
                .setTitle(R.string.subscription_devices)
                .setMessage(message)
                .setPositiveButton(R.string.close, null)
                .setNegativeButton(R.string.device_revoke_all, null)
                .create()

            dialog.setOnShowListener {
                dialog.getButton(androidx.appcompat.app.AlertDialog.BUTTON_NEGATIVE).setOnClickListener {
                    releaseDevices(token, dialog)
                }
            }
            dialog.show()
        }
    }

    private fun releaseDevices(token: String, dialog: androidx.appcompat.app.AlertDialog) {
        lifecycleScope.launch {
            try {
                withContext(Dispatchers.IO) { api.revokeAllDevices(token) }
                dialog.dismiss()
                Toast.makeText(
                    this@SubscriptionActivity,
                    R.string.device_revoke_all_done,
                    Toast.LENGTH_LONG,
                ).show()
            } catch (e: Exception) {
                Timber.w(e, "Falha ao liberar aparelhos")
                Toast.makeText(
                    this@SubscriptionActivity,
                    R.string.device_load_error,
                    Toast.LENGTH_LONG,
                ).show()
            }
        }
    }

    // ------------------------------------------------------------------
    // Cancelamento
    // ------------------------------------------------------------------

    private fun confirmCancel() {
        val current = overview ?: return
        val subscriptionId = current.subscriptionId ?: return
        val token = session.accessToken() ?: return

        MaterialAlertDialogBuilder(this)
            .setTitle(R.string.subscription_cancel_title)
            .setMessage(R.string.subscription_cancel_message)
            .setPositiveButton(R.string.subscription_cancel_confirm) { _, _ ->
                cancelSubscription(token, subscriptionId)
            }
            .setNegativeButton(R.string.back, null)
            .show()
    }

    private fun cancelSubscription(token: String, subscriptionId: String) {
        lifecycleScope.launch {
            try {
                withContext(Dispatchers.IO) { api.cancelSubscription(token, subscriptionId) }
                Toast.makeText(
                    this@SubscriptionActivity,
                    R.string.subscription_cancel_done,
                    Toast.LENGTH_LONG,
                ).show()
                load(silent = true)
            } catch (e: Exception) {
                Timber.w(e, "Falha ao cancelar a assinatura")
                showLoadError(getString(R.string.subscription_cancel_error))
            }
        }
    }

    // ------------------------------------------------------------------
    // Utilidades
    // ------------------------------------------------------------------

    /** Formata a data ISO do backend (UTC) no padrao brasileiro. */
    private fun formatDate(iso: String?): String? {
        if (iso.isNullOrBlank()) return null
        val match = Regex("""(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})""")
            .find(iso) ?: return null
        return try {
            val parser = SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss", Locale.US).apply {
                timeZone = TimeZone.getTimeZone("UTC")
            }
            val date = parser.parse(match.value) ?: return null
            // O app e em portugues: nao herdar o idioma do aparelho ("Nov 6, 2027").
            DateFormat.getDateInstance(DateFormat.MEDIUM, Locale("pt", "BR")).format(date)
        } catch (e: Exception) {
            null
        }
    }
}
