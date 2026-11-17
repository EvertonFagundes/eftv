package com.eftv.android

import android.Manifest
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.media.projection.MediaProjectionManager
import android.net.nsd.NsdManager
import android.net.nsd.NsdServiceInfo
import android.net.wifi.WifiManager
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.Gravity
import android.view.View
import android.widget.LinearLayout
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import com.eftv.android.cast.CastProtocol
import com.eftv.android.cast.CastService
import com.eftv.android.cast.CastStatus
import com.eftv.android.databinding.ActivityCastSendBinding
import com.google.android.material.button.MaterialButton
import timber.log.Timber
import java.net.Inet4Address
/**
 * "Transmitir tela": manda a tela do celular para a TV.
 *
 * A TV (ou outro aparelho com o EFTV) mostra um PIN e fica anunciada na rede
 * via mDNS. Aqui o cliente digita o PIN, escolhe a TV, autoriza a captura no
 * dialogo do Android e pode abrir qualquer app - a transmissao continua num
 * servico em primeiro plano.
 */
class CastSendActivity : AppCompatActivity() {

    private lateinit var binding: ActivityCastSendBinding

    private data class Device(val name: String, val host: String, val port: Int)

    private val devices = LinkedHashMap<String, Device>()
    private var pendingDevice: Device? = null
    private var withAudio = false

    private var nsdManager: NsdManager? = null
    private var discoveryListener: NsdManager.DiscoveryListener? = null
    private var multicastLock: WifiManager.MulticastLock? = null
    private var resolving = false
    private val resolveQueue = ArrayDeque<NsdServiceInfo>()

    private val handler = Handler(Looper.getMainLooper())
    private val ticker = object : Runnable {
        override fun run() {
            render()
            if (CastService.status.isActive) handler.postDelayed(this, STATUS_INTERVAL_MS)
        }
    }

    private val captureLauncher = registerForActivityResult(
        ActivityResultContracts.StartActivityForResult(),
    ) { result ->
        val device = pendingDevice
        pendingDevice = null
        val data = result.data
        if (result.resultCode == RESULT_OK && data != null && device != null) {
            CastService.start(
                this,
                result.resultCode,
                data,
                device.host,
                device.port,
                currentPin(),
                withAudio,
            )
            render()
            handler.removeCallbacks(ticker)
            handler.post(ticker)
        } else {
            Toast.makeText(this, getString(R.string.cast_capture_denied), Toast.LENGTH_LONG).show()
            render()
        }
    }

    /** Pede o microfone uma vez; negado, transmite so a imagem. */
    private val audioPermission = registerForActivityResult(
        ActivityResultContracts.RequestPermission(),
    ) { granted ->
        withAudio = granted
        if (!granted) {
            Toast.makeText(this, getString(R.string.cast_audio_denied), Toast.LENGTH_LONG).show()
        }
        launchProjection()
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityCastSendBinding.inflate(layoutInflater)
        setContentView(binding.root)

        binding.toolbar.setNavigationOnClickListener { finish() }
        binding.connectButton.setOnClickListener { connectManual() }
        binding.castStopButton.setOnClickListener {
            CastService.stop(this)
            render()
        }
        render()
    }

    override fun onResume() {
        super.onResume()
        acquireMulticastLock()
        render()
        handler.removeCallbacks(ticker)
        handler.postDelayed(ticker, STATUS_INTERVAL_MS)
        if (!CastService.status.isActive) startDiscovery()
    }

    override fun onPause() {
        handler.removeCallbacks(ticker)
        stopDiscovery()
        releaseMulticastLock()
        super.onPause()
    }

    private fun currentPin(): String = binding.pinInput.text?.toString()?.trim().orEmpty()

    private fun startCapture(device: Device) {
        val pin = currentPin()
        if (pin.length != 4) {
            binding.pinLayout.error = getString(R.string.cast_pin_required)
            binding.pinInput.requestFocus()
            return
        }
        binding.pinLayout.error = null
        binding.castError.visibility = View.GONE
        pendingDevice = device

        val audioGranted = Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q &&
            ContextCompat.checkSelfPermission(
                this,
                Manifest.permission.RECORD_AUDIO,
            ) == PackageManager.PERMISSION_GRANTED
        withAudio = audioGranted
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q && !audioGranted) {
            // Android 10+ e o unico que captura o som de outros apps.
            audioPermission.launch(Manifest.permission.RECORD_AUDIO)
        } else {
            launchProjection()
        }
    }

    private fun launchProjection() {
        val manager = getSystemService(Context.MEDIA_PROJECTION_SERVICE) as MediaProjectionManager
        runCatching { captureLauncher.launch(manager.createScreenCaptureIntent()) }
            .onFailure {
                Timber.w(it, "Falha ao pedir permissao de captura")
                Toast.makeText(this, getString(R.string.cast_capture_unavailable), Toast.LENGTH_LONG).show()
            }
    }

    private fun connectManual() {
        val raw = binding.manualAddress.text?.toString()?.trim().orEmpty()
        if (raw.isBlank()) {
            binding.manualLayout.error = getString(R.string.cast_address_required)
            return
        }
        val host = raw.substringBefore(':').trim()
        val port = raw.substringAfter(':', "").trim().toIntOrNull() ?: CastProtocol.DEFAULT_PORT
        if (host.isBlank() || port !in 1..65535) {
            binding.manualLayout.error = getString(R.string.cast_address_invalid)
            return
        }
        binding.manualLayout.error = null
        startCapture(Device(name = host, host = host, port = port))
    }

    // ------------------------------------------------------------------
    // Descoberta na rede (mDNS/NSD)
    // ------------------------------------------------------------------

    private fun startDiscovery() {
        if (discoveryListener != null) return
        val nsd = getSystemService(Context.NSD_SERVICE) as NsdManager
        nsdManager = nsd

        val listener = object : NsdManager.DiscoveryListener {
            override fun onDiscoveryStarted(serviceType: String) {
                runOnUiThread { binding.castDiscovering.visibility = View.VISIBLE }
            }

            override fun onServiceFound(info: NsdServiceInfo) {
                if (!info.serviceType.startsWith(CastProtocol.SERVICE_TYPE)) return
                resolve(info)
            }

            override fun onServiceLost(info: NsdServiceInfo) {
                runOnUiThread {
                    val key = devices.keys.firstOrNull { it.startsWith("${info.serviceName}@") }
                    if (key != null) {
                        devices.remove(key)
                        renderDevices()
                    }
                }
            }

            override fun onDiscoveryStopped(serviceType: String) {
                runOnUiThread { binding.castDiscovering.visibility = View.GONE }
            }

            override fun onStartDiscoveryFailed(serviceType: String, errorCode: Int) {
                Timber.w("Descoberta de TVs falhou: %s", errorCode)
                runOnUiThread { stopDiscovery() }
            }

            override fun onStopDiscoveryFailed(serviceType: String, errorCode: Int) {
                Timber.w("Parar descoberta falhou: %s", errorCode)
            }
        }
        discoveryListener = listener
        runCatching { nsd.discoverServices(CastProtocol.SERVICE_TYPE, NsdManager.PROTOCOL_DNS_SD, listener) }
            .onFailure {
                Timber.w(it, "Nao foi possivel iniciar a descoberta")
                discoveryListener = null
            }
    }

    @Suppress("DEPRECATION")
    private fun resolve(info: NsdServiceInfo) {
        synchronized(resolveQueue) { resolveQueue.addLast(info) }
        resolveNext()
    }

    /**
     * O `NsdManager` aceita uma resolucao por vez; enfileirar permite mostrar
     * mais de uma TV na mesma rede sem perder a segunda.
     */
    @Suppress("DEPRECATION")
    private fun resolveNext() {
        val current: NsdServiceInfo
        synchronized(resolveQueue) {
            if (resolving) return
            current = resolveQueue.removeFirstOrNull() ?: return
            resolving = true
        }
        val nsd = nsdManager ?: run {
            synchronized(resolveQueue) { resolving = false }
            return
        }
        runCatching {
            nsd.resolveService(current, object : NsdManager.ResolveListener {
                override fun onServiceResolved(service: NsdServiceInfo) {
                    val address = service.host
                    val host = (address as? Inet4Address)?.hostAddress ?: address?.hostAddress
                    if (!host.isNullOrBlank()) {
                        val name = service.serviceName.ifBlank { "EFTV" }
                        val device = Device(name, host, service.port)
                        runOnUiThread {
                            devices["$name@$host:${service.port}"] = device
                            renderDevices()
                        }
                    }
                    finishResolve()
                }

                override fun onResolveFailed(service: NsdServiceInfo, errorCode: Int) {
                    Timber.w("Nao resolveu %s: %s", service.serviceName, errorCode)
                    finishResolve()
                }
            })
        }.onFailure {
            Timber.w(it, "Falha ao resolver servico")
            finishResolve()
        }
    }

    private fun finishResolve() {
        synchronized(resolveQueue) { resolving = false }
        resolveNext()
    }

    private fun stopDiscovery() {
        val listener = discoveryListener ?: return
        discoveryListener = null
        synchronized(resolveQueue) {
            resolveQueue.clear()
            resolving = false
        }
        runCatching { nsdManager?.stopServiceDiscovery(listener) }
        binding.castDiscovering.visibility = View.GONE
    }

    // ------------------------------------------------------------------
    // Interface
    // ------------------------------------------------------------------

    private fun render() {
        val status = CastService.status
        val active = status.isActive
        binding.runningPanel.visibility = if (active) View.VISIBLE else View.GONE
        binding.idlePanel.visibility = if (active) View.GONE else View.VISIBLE

        if (active) {
            binding.castStatus.text = when (status.state) {
                CastStatus.State.STREAMING -> getString(R.string.cast_send_streaming)
                else -> status.message.ifBlank { getString(R.string.cast_send_connecting) }
            }
        }

        if (status.state == CastStatus.State.ERROR) {
            binding.castError.text = status.message
            binding.castError.visibility = View.VISIBLE
        } else {
            binding.castError.visibility = View.GONE
        }

        if (active) stopDiscovery()
        renderDevices()
    }

    private fun renderDevices() {
        binding.deviceList.removeAllViews()
        val active = CastService.status.isActive
        val list = devices.values.toList()
        binding.discoveryEmpty.visibility =
            if (list.isEmpty() && !active) View.VISIBLE else View.GONE
        binding.castDiscovering.visibility =
            if (list.isEmpty() && discoveryListener != null) View.VISIBLE else View.GONE

        val margin = (8 * resources.displayMetrics.density).toInt()
        for (device in list) {
            val button = MaterialButton(
                this,
                null,
                com.google.android.material.R.attr.materialButtonOutlinedStyle,
            ).apply {
                text = getString(R.string.cast_device_button, device.name, device.host)
                isAllCaps = false
                gravity = Gravity.START or Gravity.CENTER_VERTICAL
                isEnabled = !active
                setOnClickListener { startCapture(device) }
            }
            binding.deviceList.addView(
                button,
                LinearLayout.LayoutParams(
                    LinearLayout.LayoutParams.MATCH_PARENT,
                    LinearLayout.LayoutParams.WRAP_CONTENT,
                ).apply { topMargin = margin },
            )
        }
    }

    private fun acquireMulticastLock() {
        if (multicastLock?.isHeld == true) return
        val wifi = applicationContext.getSystemService(Context.WIFI_SERVICE) as? WifiManager ?: return
        multicastLock = runCatching {
            wifi.createMulticastLock("eftv-cast").apply {
                setReferenceCounted(false)
                acquire()
            }
        }.getOrNull()
    }

    private fun releaseMulticastLock() {
        runCatching { multicastLock?.release() }
        multicastLock = null
    }

    private companion object {
        const val STATUS_INTERVAL_MS = 800L
    }
}
