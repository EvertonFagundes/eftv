package com.eftv.android

import android.app.NotificationManager
import android.app.Service
import android.content.Context
import android.content.Intent
import android.net.ConnectivityManager
import android.net.Network
import android.os.Build
import android.os.IBinder
import com.chaquo.python.Python
import timber.log.Timber
import java.io.File
import java.io.FileOutputStream
import kotlin.concurrent.thread

/**
 * Sobe o servidor Python embutido (proxy dos streams + catalogo).
 *
 * Nao e um servico de primeiro plano: nada de notificacao fixa na barra. O
 * preco e que o Android pode encerrar o processo quando o app fica muito tempo
 * em segundo plano; nesse caso o servidor volta junto com o app, que e o unico
 * consumidor dele.
 *
 * Tambem nao segura wake lock: as telas que usam o servidor (catalogo, player,
 * transmissao) mantem a tela ligada, entao segurar a CPU acordada em segundo
 * plano so gastava bateria.
 */
class EftvServerService : Service() {

    private var networkCallback: ConnectivityManager.NetworkCallback? = null

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        clearLegacyChannel()
        startNetworkMonitoring()
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
                if (ok) {
                    com.eftv.android.data.LocalServer.markReady()
                } else {
                    Timber.e(
                        "Servidor EFTV nao subiu: %s",
                        result.callAttr("get", "error", "falha").toString(),
                    )
                }
            } catch (e: Exception) {
                Timber.e(e, "Falha ao iniciar servidor EFTV")
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
        super.onDestroy()
    }

    /**
     * Apaga o canal de notificacao da versao antiga, quando o servidor rodava
     * em primeiro plano. Canais sobrevivem a atualizacao do APK e ficariam
     * aparecendo vazios em Configuracoes -> Notificacoes.
     */
    private fun clearLegacyChannel() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        val manager = getSystemService(NotificationManager::class.java) ?: return
        runCatching { manager.deleteNotificationChannel("eftv_server") }
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
            // A rede costuma levar alguns segundos para ficar realmente valida:
            // tenta por ate 12 s antes de reiniciar (antes reiniciava no
            // primeiro teste, derrubando um servidor que estava saudavel).
            repeat(6) {
                Thread.sleep(2_000)
                if (servidorRespondendo()) {
                    Timber.i("Servidor EFTV respondeu apos mudanca de rede")
                    return@thread
                }
            }
            Timber.w("Servidor EFTV nao respondeu; reiniciando")
            reiniciarServidor()
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

    companion object {
        const val PORT = 8124

        /**
         * So o proprio aparelho acessa o servidor.
         *
         * Com `0.0.0.0` qualquer um no mesmo Wi-Fi alcancava o proxy e podia
         * usa-lo para buscar URLs arbitrarias (proxy aberto). Nada no app
         * precisa de acesso externo: o player e o catalogo falam por loopback.
         */
        const val HOST = "127.0.0.1"

        /**
         * Inicia o servidor. Sem primeiro plano, o Android 8+ recusa iniciar
         * um servico com o app em segundo plano: nesse caso o app tenta de
         * novo ao abrir a tela principal.
         */
        fun start(context: Context) {
            val intent = Intent(context, EftvServerService::class.java)
            runCatching { context.startService(intent) }
                .onFailure { Timber.w(it, "Servidor local sera iniciado com o app aberto") }
        }
    }
}
