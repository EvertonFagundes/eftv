package com.eftv.android.cast

import android.app.Activity
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.media.projection.MediaProjection
import android.media.projection.MediaProjectionManager
import android.os.Build
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.os.SystemClock
import androidx.core.app.NotificationCompat
import androidx.core.app.ServiceCompat
import androidx.core.content.ContextCompat
import androidx.core.content.IntentCompat
import com.eftv.android.CastSendActivity
import com.eftv.android.R
import timber.log.Timber

/**
 * Mantem a transmissao de tela viva mesmo com o app em segundo plano.
 *
 * Isso e obrigatorio para o recurso fazer sentido: o cliente abre o YouTube,
 * o Instagram ou a galeria e continua vendo tudo na TV. No Android 14 a
 * captura so pode ser criada depois de um servico em primeiro plano com
 * `foregroundServiceType="mediaProjection"`, e o sistema derruba a captura se
 * esse servico parar.
 */
class CastService : Service() {

    private var sender: CastSender? = null

    /** Quando a transmissao comecou, para saber se a captura durou pouco. */
    private var startedAt = 0L

    private val handler = Handler(Looper.getMainLooper())
    private var pendingStop: Runnable? = null

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        Timber.i("CastService: onStart action=%s startId=%d", intent?.action ?: "null", startId)
        when (intent?.action) {
            ACTION_START -> startCasting(intent)
            ACTION_STOP -> stopSelf()
            else -> {
                // Reinicio do sistema com intent nulo: nao ha como retomar uma
                // captura sem a permissao do usuario.
                Timber.w("CastService: parado por intent sem acao")
                stopSelf()
            }
        }
        return START_NOT_STICKY
    }

    private fun startCasting(intent: Intent) {
        // Uma tentativa nova cancela o encerramento agendado pela anterior:
        // sem isso, o stopSelf atrasado derrubaria a transmissao recem-iniciada.
        cancelPendingStop()
        // E encerra a transmissao anterior, se o usuario tocou em Conectar de novo.
        sender?.stop()
        sender = null
        startedAt = SystemClock.elapsedRealtime()
        startInForeground()
        Timber.i("CastService: primeiro plano ativo")

        val resultCode = intent.getIntExtra(EXTRA_RESULT_CODE, Activity.RESULT_CANCELED)
        val data = IntentCompat.getParcelableExtra(intent, EXTRA_DATA, Intent::class.java)
        if (data == null) {
            fail("Permissão de captura expirada. Tente de novo.")
            return
        }
        val host = intent.getStringExtra(EXTRA_HOST).orEmpty()
        val port = intent.getIntExtra(EXTRA_PORT, CastProtocol.DEFAULT_PORT)
        val pin = intent.getStringExtra(EXTRA_PIN).orEmpty()
        val withAudio = intent.getBooleanExtra(EXTRA_AUDIO, false)
        if (host.isBlank() || pin.length < 4) {
            fail("Dados da conexão incompletos")
            return
        }
        Timber.i("CastService: destino %s:%d audio=%s", host, port, withAudio)

        val manager = getSystemService(Context.MEDIA_PROJECTION_SERVICE) as MediaProjectionManager
        val projection = runCatching { manager.getMediaProjection(resultCode, data) }
            .onFailure { Timber.e(it, "CastService: getMediaProjection falhou") }
            .getOrNull()
        if (projection == null) {
            fail("Não foi possível capturar a tela")
            return
        }
        Timber.i("CastService: projecao obtida")

        val cast = CastSender(this, projection, host, port, pin, withAudio) { newStatus ->
            status = newStatus
            updateNotification(newStatus)
            if (newStatus.state == CastStatus.State.ERROR) {
                // Deixa a mensagem visivel antes de encerrar o servico.
                scheduleStop()
            }
        }
        sender = cast

        // O Android 14 exige o callback registrado ANTES de criar o display.
        // O callback fica preso a ESTA sessao: se o usuario conectar de novo,
        // a projecao antiga fecha e nao pode derrubar a transmissao nova.
        projection.registerCallback(
            object : MediaProjection.Callback() {
                override fun onStop() {
                    if (sender !== cast) {
                        Timber.i("Captura de uma sessao antiga encerrada; ignorando")
                        return
                    }
                    val aliveMs = SystemClock.elapsedRealtime() - startedAt
                    val ownCleanup = cast.isStopping
                    Timber.i(
                        "Captura de tela encerrada (%d ms, estado=%s, por nos=%s)",
                        aliveMs,
                        status.state,
                        ownCleanup,
                    )
                    if (ownCleanup) {
                        // Foi o proprio CastSender que soltou a projecao ao
                        // falhar ou parar. O motivo real (rede, PIN, botao
                        // Parar) ja foi publicado em `status`; sobrescrever
                        // aqui esconderia a mensagem do cliente.
                        return
                    }
                    cast.stop()
                    // O sistema derrubou a captura (tela bloqueada, "Parar" no
                    // aviso do Android, app restrito). Se nenhuma imagem chegou,
                    // o usuario precisa saber o motivo.
                    status = if (status.state != CastStatus.State.STREAMING) {
                        CastStatus(CastStatus.State.ERROR, getString(R.string.cast_capture_stopped))
                    } else {
                        CastStatus.IDLE
                    }
                    stopSelf()
                }
            },
            handler,
        )

        cast.start()
    }

    private fun fail(message: String) {
        val error = CastStatus(CastStatus.State.ERROR, message)
        status = error
        updateNotification(error)
        scheduleStop()
    }

    private fun scheduleStop() {
        cancelPendingStop()
        val runnable = Runnable { stopSelf() }
        pendingStop = runnable
        handler.postDelayed(runnable, ERROR_LINGER_MS)
    }

    private fun cancelPendingStop() {
        pendingStop?.let(handler::removeCallbacks)
        pendingStop = null
    }

    private fun startInForeground() {
        createChannel()
        val notification = buildNotification(CastStatus(CastStatus.State.CONNECTING, "Preparando…"))
        val type = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PROJECTION
        } else {
            0
        }
        ServiceCompat.startForeground(this, NOTIFICATION_ID, notification, type)
    }

    private fun updateNotification(current: CastStatus) {
        val notification = buildNotification(current)
        val manager = getSystemService(NOTIFICATION_SERVICE) as NotificationManager
        runCatching { manager.notify(NOTIFICATION_ID, notification) }
    }

    private fun buildNotification(current: CastStatus): Notification {
        val open = PendingIntent.getActivity(
            this,
            0,
            Intent(this, CastSendActivity::class.java),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
        val stop = PendingIntent.getService(
            this,
            1,
            Intent(this, CastService::class.java).setAction(ACTION_STOP),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_devices)
            .setContentTitle(getString(R.string.cast_notification_title))
            .setContentText(current.message.ifBlank { getString(R.string.cast_notification_text) })
            .setContentIntent(open)
            .setOngoing(current.isActive)
            .setSilent(true)
            .addAction(0, getString(R.string.cast_stop), stop)
            .build()
    }

    private fun createChannel() {
        val manager = getSystemService(NOTIFICATION_SERVICE) as NotificationManager
        if (manager.getNotificationChannel(CHANNEL_ID) != null) return
        manager.createNotificationChannel(
            NotificationChannel(
                CHANNEL_ID,
                getString(R.string.cast_notification_channel),
                NotificationManager.IMPORTANCE_LOW,
            ).apply {
                description = getString(R.string.cast_notification_channel_description)
                setShowBadge(false)
            },
        )
    }

    override fun onDestroy() {
        Timber.i("CastService: onDestroy (estado=%s)", status.state)
        cancelPendingStop()
        sender?.stop()
        sender = null
        // Um erro precisa continuar visivel na tela que pediu a transmissao.
        if (status.state != CastStatus.State.ERROR) status = CastStatus.IDLE
        runCatching { stopForeground(true) }
        super.onDestroy()
    }

    companion object {
        /** Ultimo estado conhecido (lido pelas telas sem bind). */
        @Volatile
        var status: CastStatus = CastStatus.IDLE

        private const val CHANNEL_ID = "eftv-cast"
        private const val NOTIFICATION_ID = 4310
        private const val ERROR_LINGER_MS = 6_000L
        private const val ACTION_START = "com.eftv.android.cast.action.START"
        private const val ACTION_STOP = "com.eftv.android.cast.action.STOP"
        private const val EXTRA_RESULT_CODE = "result_code"
        private const val EXTRA_DATA = "result_data"
        private const val EXTRA_HOST = "host"
        private const val EXTRA_PORT = "port"
        private const val EXTRA_PIN = "pin"
        private const val EXTRA_AUDIO = "audio"

        fun start(
            context: Context,
            resultCode: Int,
            data: Intent,
            host: String,
            port: Int,
            pin: String,
            withAudio: Boolean = false,
        ) {
            status = CastStatus(CastStatus.State.CONNECTING, "Conectando a $host…")
            val intent = Intent(context, CastService::class.java)
                .setAction(ACTION_START)
                .putExtra(EXTRA_RESULT_CODE, resultCode)
                .putExtra(EXTRA_DATA, data)
                .putExtra(EXTRA_HOST, host)
                .putExtra(EXTRA_PORT, port)
                .putExtra(EXTRA_PIN, pin)
                .putExtra(EXTRA_AUDIO, withAudio)
            ContextCompat.startForegroundService(context, intent)
        }

        fun stop(context: Context) {
            context.stopService(Intent(context, CastService::class.java))
            status = CastStatus.IDLE
        }
    }
}
