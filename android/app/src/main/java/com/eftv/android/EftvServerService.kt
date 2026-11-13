package com.eftv.android

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.net.ConnectivityManager
import android.net.Network
import android.os.Build
import android.os.IBinder
import android.os.PowerManager
import androidx.core.app.NotificationCompat
import androidx.core.content.ContextCompat
import com.chaquo.python.Python
import timber.log.Timber
import java.io.File
import java.io.FileOutputStream
import kotlin.concurrent.thread

class EftvServerService : Service() {

    private var wakeLock: PowerManager.WakeLock? = null
    private var networkCallback: ConnectivityManager.NetworkCallback? = null

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        createChannel()
        acquireWakeLock()
        startNetworkMonitoring()
        startInForeground("Iniciando servidor local...")
        thread(name = "eftv-server-boot", isDaemon = true) {
            try {
                val www = syncAssets()
                val data = File(filesDir, "eftv-data").apply { mkdirs() }
                val result = Python.getInstance()
                    .getModule("eftv_runner")
                    .callAttr(
                        "start_server",
                        www.absolutePath,
                        data.absolutePath,
                        HOST,
                        PORT,
                    )
                Timber.i("Servidor EFTV: %s", result.toString())
                val ok = result.callAttr("get", "ok").toBoolean()
                if (ok) com.eftv.android.data.LocalServer.markReady()
                val text = if (ok) {
                    getString(R.string.server_notification_text, PORT)
                } else {
                    result.callAttr("get", "error", "falha").toString()
                }
                notify(text)
            } catch (e: Exception) {
                Timber.e(e, "Falha ao iniciar servidor EFTV")
                notify(e.message ?: "Falha ao iniciar servidor")
            }
        }
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int = START_STICKY

    override fun onDestroy() {
        stopNetworkMonitoring()
        try {
            if (Python.isStarted()) {
                Python.getInstance().getModule("eftv_runner").callAttr("stop_server")
            }
        } catch (e: Exception) {
            Timber.w(e, "Falha ao parar servidor EFTV")
        }
        releaseWakeLock()
        super.onDestroy()
    }

    /**
     * Fica de olho na rede do aparelho.
     *
     * Quando o usuario sai do Wi-Fi e entra nos dados moveis (ou o contrario),
     * o socket do servidor Python pode ficar preso na interface antiga. Se o
     * servidor parar de responder, reiniciamos para ele voltar a atender.
     */
    private fun startNetworkMonitoring() {
        val cm = getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
        val callback = object : ConnectivityManager.NetworkCallback() {
            override fun onAvailable(network: Network) {
                super.onAvailable(network)
                Timber.i("Rede disponivel: %s", network)
                verificarServidorAposMudancaDeRede()
            }

            override fun onLost(network: Network) {
                super.onLost(network)
                Timber.i("Rede perdida: %s", network)
            }
        }
        networkCallback = callback
        cm.registerDefaultNetworkCallback(callback)
    }

    private fun stopNetworkMonitoring() {
        val callback = networkCallback ?: return
        networkCallback = null
        val cm = getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
        runCatching { cm.unregisterNetworkCallback(callback) }
    }

    /** Espera a rede assentar e reinicia o servidor se ele nao responder. */
    private fun verificarServidorAposMudancaDeRede() {
        thread(name = "eftv-server-netcheck", isDaemon = true) {
            // A rede costuma levar alguns segundos para ficar realmente valida.
            repeat(6) {
                Thread.sleep(2_000)
                if (servidorRespondendo()) {
                    Timber.i("Servidor EFTV respondeu apos mudanca de rede")
                    return@thread
                }
                Timber.w("Servidor EFTV nao respondeu; reiniciando")
                reiniciarServidor()
                return@thread
            }
        }
    }

    private fun servidorRespondendo(): Boolean = try {
        val conn = java.net.URL("http://127.0.0.1:$PORT/api/status")
            .openConnection() as java.net.HttpURLConnection
        conn.connectTimeout = 3_000
        conn.readTimeout = 5_000
        conn.requestMethod = "GET"
        val ok = conn.responseCode == 200
        conn.disconnect()
        ok
    } catch (_: Exception) {
        false
    }

    /** Derruba e sobe o servidor Python de novo. */
    private fun reiniciarServidor() {
        try {
            if (Python.isStarted()) {
                Python.getInstance().getModule("eftv_runner").callAttr("stop_server")
            }
        } catch (e: Exception) {
            Timber.w(e, "Falha ao parar servidor para reinicio")
        }
        try {
            val www = File(filesDir, "eftv-www")
            val data = File(filesDir, "eftv-data").apply { mkdirs() }
            val result = Python.getInstance()
                .getModule("eftv_runner")
                .callAttr("start_server", www.absolutePath, data.absolutePath, HOST, PORT)
            Timber.i("Servidor EFTV reiniciado: %s", result.toString())
            if (result.callAttr("get", "ok").toBoolean()) {
                com.eftv.android.data.LocalServer.markReady()
            }
        } catch (e: Exception) {
            Timber.e(e, "Falha ao reiniciar servidor EFTV")
        }
    }

    private fun acquireWakeLock() {
        val manager = getSystemService(POWER_SERVICE) as? PowerManager ?: return
        wakeLock = manager.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "EFTV:server").apply {
            setReferenceCounted(false)
            acquire()
        }
    }

    private fun releaseWakeLock() {
        wakeLock?.let { if (it.isHeld) it.release() }
        wakeLock = null
    }

    private fun syncAssets(): File {
        val dest = File(filesDir, "eftv-www")
        dest.mkdirs()
        val marker = File(dest, ".apk-version")
        val version = try {
            val info = packageManager.getPackageInfo(packageName, 0)
            "${info.versionCode}-${info.lastUpdateTime}"
        } catch (_: Exception) {
            "1"
        }
        if (marker.exists() && marker.readText() == version && File(dest, "index.html").isFile) {
            return dest
        }
        copyAssetDir("eftv", dest)
        marker.writeText(version)
        return dest
    }

    private fun copyAssetDir(prefix: String, dest: File) {
        val names = assets.list(prefix) ?: return
        dest.mkdirs()
        for (name in names) {
            val assetPath = "$prefix/$name"
            val children = assets.list(assetPath)
            val out = File(dest, name)
            if (children != null && children.isNotEmpty()) {
                copyAssetDir(assetPath, out)
            } else {
                assets.open(assetPath).use { input ->
                    FileOutputStream(out).use { output -> input.copyTo(output) }
                }
            }
        }
    }

    private fun createChannel() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        val manager = getSystemService(NotificationManager::class.java) ?: return
        val channel = NotificationChannel(
            CHANNEL_ID,
            getString(R.string.server_channel_name),
            NotificationManager.IMPORTANCE_LOW,
        )
        channel.setShowBadge(false)
        manager.createNotificationChannel(channel)
    }

    private fun startInForeground(text: String) {
        val notification = buildNotification(text)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
            startForeground(
                NOTIFICATION_ID,
                notification,
                ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE,
            )
        } else {
            startForeground(NOTIFICATION_ID, notification)
        }
    }

    private fun notify(text: String) {
        val manager = getSystemService(NotificationManager::class.java) ?: return
        manager.notify(NOTIFICATION_ID, buildNotification(text))
    }

    private fun buildNotification(text: String): Notification {
        val launch = packageManager.getLaunchIntentForPackage(packageName)
        val pending = PendingIntent.getActivity(
            this,
            0,
            launch,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_tv)
            .setContentTitle(getString(R.string.server_notification_title))
            .setContentText(text)
            .setOngoing(true)
            .setContentIntent(pending)
            .setForegroundServiceBehavior(NotificationCompat.FOREGROUND_SERVICE_IMMEDIATE)
            .build()
    }

    companion object {
        const val PORT = 8124
        const val HOST = "0.0.0.0"
        const val CHANNEL_ID = "eftv_server"
        const val NOTIFICATION_ID = 8124

        fun start(context: Context) {
            val intent = Intent(context, EftvServerService::class.java)
            ContextCompat.startForegroundService(context, intent)
        }
    }
}
