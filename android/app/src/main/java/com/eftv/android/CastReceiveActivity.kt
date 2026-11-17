package com.eftv.android

import android.content.Context
import android.net.nsd.NsdManager
import android.net.nsd.NsdServiceInfo
import android.os.Build
import android.os.Bundle
import android.view.Surface
import android.view.SurfaceHolder
import android.view.View
import android.view.WindowManager
import androidx.appcompat.app.AppCompatActivity
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat
import androidx.core.view.WindowInsetsControllerCompat
import com.eftv.android.cast.CastProtocol
import com.eftv.android.cast.CastServer
import com.eftv.android.cast.CastSink
import com.eftv.android.cast.H264Decoder
import com.eftv.android.databinding.ActivityCastReceiveBinding
import timber.log.Timber
import java.net.Inet4Address
import java.net.NetworkInterface

/**
 * "Receber tela": a TV (ou outro aparelho com o EFTV) mostra um PIN e espera
 * o celular mandar a tela.
 *
 * O video e decodificado pelo hardware direto na Surface, sem ExoPlayer: o
 * protocolo e proprietario e nao tem container (ver [com.eftv.android.cast.CastProtocol]).
 */
class CastReceiveActivity : AppCompatActivity(), CastSink {

    private lateinit var binding: ActivityCastReceiveBinding
    private val pin = CastProtocol.randomPin()

    private var server: CastServer? = null
    private var nsdManager: NsdManager? = null
    private var registration: NsdManager.RegistrationListener? = null
    private var decoder: H264Decoder? = null
    private var surface: Surface? = null
    private var pendingConfig: Triple<Int, Int, ByteArray>? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityCastReceiveBinding.inflate(layoutInflater)
        setContentView(binding.root)

        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        hideSystemBars()

        binding.pinText.text = pin
        binding.closeButton.setOnClickListener { finish() }
        binding.surfaceView.holder.addCallback(object : SurfaceHolder.Callback {
            override fun surfaceCreated(holder: SurfaceHolder) {
                surface = holder.surface
                openDecoderIfReady()
            }

            override fun surfaceChanged(holder: SurfaceHolder, format: Int, width: Int, height: Int) = Unit

            override fun surfaceDestroyed(holder: SurfaceHolder) {
                surface = null
                decoder?.release()
                decoder = null
            }
        })

        startServer()
        binding.closeButton.requestFocus()
    }

    private fun startServer() {
        val castServer = CastServer(pin, this) { connected, name ->
            runOnUiThread { handleConnection(connected, name) }
        }
        val port = runCatching { castServer.bind() }.getOrNull()
        if (port == null) {
            showError(getString(R.string.cast_receive_error))
            return
        }
        server = castServer

        val address = localIpv4()
        binding.addressText.text = if (address.isNullOrBlank()) {
            getString(R.string.cast_receive_no_network)
        } else {
            getString(R.string.cast_receive_address, address, port)
        }
        registerService(port)
        castServer.acceptLoop()
    }

    private fun registerService(port: Int) {
        val nsd = getSystemService(Context.NSD_SERVICE) as? NsdManager ?: return
        nsdManager = nsd
        val info = NsdServiceInfo().apply {
            serviceName = "EFTV ${Build.MODEL}".take(40)
            serviceType = CastProtocol.SERVICE_TYPE
            setPort(port)
        }
        val listener = object : NsdManager.RegistrationListener {
            override fun onServiceRegistered(info: NsdServiceInfo) {
                Timber.i("TV anunciada na rede como %s", info.serviceName)
            }

            override fun onRegistrationFailed(info: NsdServiceInfo, errorCode: Int) {
                // Nao e fatal: o celular ainda pode conectar pelo endereco.
                Timber.w("Nao foi possivel anunciar a TV: %s", errorCode)
            }

            override fun onServiceUnregistered(info: NsdServiceInfo) = Unit

            override fun onUnregistrationFailed(info: NsdServiceInfo, errorCode: Int) = Unit
        }
        registration = listener
        runCatching { nsd.registerService(info, NsdManager.PROTOCOL_DNS_SD, listener) }
            .onFailure { Timber.w(it, "Falha ao anunciar a TV na rede") }
    }

    // ------------------------------------------------------------------
    // Sinais do servidor (thread de rede)
    // ------------------------------------------------------------------

    override fun onConfig(width: Int, height: Int, csd: ByteArray) {
        runOnUiThread {
            pendingConfig = Triple(width, height, csd)
            openDecoderIfReady()
        }
    }

    override fun onVideo(data: ByteArray, ptsUs: Long) {
        decoder?.video(data, ptsUs)
    }

    private fun openDecoderIfReady() {
        val config = pendingConfig ?: return
        val currentSurface = surface ?: return
        decoder?.release()
        binding.videoFrame.setAspectRatio(config.first.toFloat() / config.second)
        val newDecoder = H264Decoder(currentSurface) { message ->
            runOnUiThread {
                showError(message)
                handleConnection(false, null)
            }
        }
        newDecoder.configure(config.first, config.second, config.third)
        decoder = newDecoder
    }

    private fun handleConnection(connected: Boolean, deviceName: String?) {
        if (isFinishing || isDestroyed) return
        if (connected) {
            binding.waitingPanel.visibility = View.GONE
            binding.videoFrame.visibility = View.VISIBLE
            binding.castError.visibility = View.GONE
            Timber.i("Recebendo tela de %s", deviceName)
        } else {
            decoder?.release()
            decoder = null
            pendingConfig = null
            binding.videoFrame.visibility = View.GONE
            binding.waitingPanel.visibility = View.VISIBLE
            binding.closeButton.requestFocus()
        }
    }

    private fun showError(message: String) {
        binding.castError.text = message
        binding.castError.visibility = View.VISIBLE
    }

    /** Primeiro IPv4 da rede local, para o cliente digitar no modo manual. */
    private fun localIpv4(): String? = runCatching {
        NetworkInterface.getNetworkInterfaces().toList()
            .asSequence()
            .filter { it.isUp && !it.isLoopback }
            .flatMap { it.inetAddresses.toList().asSequence() }
            .filterIsInstance<Inet4Address>()
            .firstOrNull { it.isSiteLocalAddress }
            ?.hostAddress
    }.getOrNull()

    private fun hideSystemBars() {
        WindowCompat.setDecorFitsSystemWindows(window, false)
        val controller = WindowInsetsControllerCompat(window, binding.root)
        controller.hide(WindowInsetsCompat.Type.systemBars())
        controller.systemBarsBehavior =
            WindowInsetsControllerCompat.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
    }

    override fun onDestroy() {
        server?.stop()
        server = null
        decoder?.release()
        decoder = null
        runCatching { registration?.let { nsdManager?.unregisterService(it) } }
        registration = null
        super.onDestroy()
    }
}
