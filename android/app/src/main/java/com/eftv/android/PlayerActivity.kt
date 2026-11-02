package com.eftv.android

import android.media.AudioManager
import android.net.Uri
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import android.view.View
import android.view.WindowManager
import androidx.appcompat.app.AppCompatActivity
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat
import androidx.core.view.WindowInsetsControllerCompat
import androidx.media3.common.AudioAttributes
import androidx.media3.common.MediaItem
import androidx.media3.common.MediaMetadata
import androidx.media3.common.PlaybackException
import androidx.media3.common.Player
import androidx.media3.datasource.DefaultHttpDataSource
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.exoplayer.source.DefaultMediaSourceFactory
import com.eftv.android.databinding.ActivityPlayerBinding
import timber.log.Timber

/**
 * Player de um canal. Como transmissao ao vivo de IPTV costuma ser encerrada
 * pelo servidor depois de alguns segundos (ou sofrer queda de rede), o player
 * se reconecta sozinho e volta para o ponto ao vivo, sem parar no fim do stream.
 */
class PlayerActivity : AppCompatActivity() {

    private lateinit var binding: ActivityPlayerBinding
    private var player: ExoPlayer? = null

    private lateinit var streamUrl: String
    private var channelName: String = ""
    private var channelLogo: String = ""
    private var userAgent: String = PlaylistConfig.USER_AGENT
    private var referer: String? = null

    private val handler = Handler(Looper.getMainLooper())
    private var reconnectAttempt = 0
    private var reconnectPending = false
    private var lastReadyAt = 0L
    private var lastErrorDetail: String? = null
    private var stopped = false

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityPlayerBinding.inflate(layoutInflater)
        setContentView(binding.root)

        streamUrl = intent.getStringExtra(EXTRA_URL) ?: run {
            finish()
            return
        }
        channelName = intent.getStringExtra(EXTRA_NAME).orEmpty()
        channelLogo = intent.getStringExtra(EXTRA_LOGO).orEmpty()
        userAgent = intent.getStringExtra(EXTRA_USER_AGENT) ?: PlaylistConfig.USER_AGENT
        referer = intent.getStringExtra(EXTRA_REFERER)

        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        volumeControlStream = AudioManager.STREAM_MUSIC
        hideSystemBars()

        binding.retryButton.setOnClickListener { startPlayback() }
        binding.backButton.setOnClickListener { finish() }
    }

    override fun onStart() {
        super.onStart()
        stopped = false
        if (::binding.isInitialized && this::streamUrl.isInitialized && !isFinishing) {
            // Sempre (re)comeca do ponto ao vivo ao abrir/voltar para a tela.
            startPlayback()
        }
    }

    override fun onStop() {
        super.onStop()
        stopped = true
        releasePlayer()
    }

    // ------------------------------------------------------------------
    // Player
    // ------------------------------------------------------------------

    private fun startPlayback() {
        reconnectAttempt = 0
        lastReadyAt = 0L
        lastErrorDetail = null
        hideError()
        hideReconnecting()
        preparePlayer()
    }

    private fun preparePlayer() {
        releasePlayer()

        val httpFactory = DefaultHttpDataSource.Factory()
            .setUserAgent(userAgent)
            .setConnectTimeoutMs(15_000)
            .setReadTimeoutMs(20_000)
            .setAllowCrossProtocolRedirects(true)

        referer?.takeIf { it.isNotBlank() }?.let { value ->
            httpFactory.setDefaultRequestProperties(mapOf("Referer" to value))
        }

        val mediaSourceFactory = DefaultMediaSourceFactory(this)
            .setDataSourceFactory(httpFactory)

        val exoPlayer = ExoPlayer.Builder(this)
            .setMediaSourceFactory(mediaSourceFactory)
            .build()

        exoPlayer.setAudioAttributes(AudioAttributes.DEFAULT, /* handleAudioFocus = */ true)
        exoPlayer.setHandleAudioBecomingNoisy(true)

        val metadata = MediaMetadata.Builder()
            .setTitle(channelName)
            .apply { if (channelLogo.isNotBlank()) setArtworkUri(Uri.parse(channelLogo)) }
            .build()

        exoPlayer.addListener(object : Player.Listener {
            override fun onPlayerError(error: PlaybackException) {
                Timber.e(error, "Erro ao reproduzir %s", streamUrl)
                lastErrorDetail = buildString {
                    append(error.errorCodeName)
                    error.cause?.message?.let { append(": ").append(it) }
                }
                scheduleReconnect()
            }

            override fun onPlaybackStateChanged(playbackState: Int) {
                when (playbackState) {
                    Player.STATE_READY -> {
                        resetBackoffIfStable()
                        lastReadyAt = SystemClock.elapsedRealtime()
                        hideError()
                        hideReconnecting()
                    }

                    Player.STATE_ENDED -> {
                        // Muitos servidores IPTV fecham o stream depois de N segundos.
                        lastErrorDetail = getString(R.string.stream_ended_by_server)
                        scheduleReconnect()
                    }
                }
            }
        })

        binding.playerView.player = exoPlayer
        exoPlayer.setMediaItem(
            MediaItem.Builder()
                .setUri(streamUrl)
                .setMediaMetadata(metadata)
                .build()
        )
        exoPlayer.prepare()
        exoPlayer.playWhenReady = true
        player = exoPlayer
    }

    // ------------------------------------------------------------------
    // Reconexao automatica
    // ------------------------------------------------------------------

    private fun scheduleReconnect() {
        if (stopped || isFinishing || isDestroyed || reconnectPending) return

        reconnectPending = true
        reconnectAttempt++
        val delayMs = delayFor(reconnectAttempt)
        showReconnecting(reconnectAttempt)

        if (reconnectAttempt >= SHOW_ERROR_AFTER) {
            showError(lastErrorDetail ?: getString(R.string.player_error_title))
        }

        Timber.i("Reconectando em %d ms (tentativa %d)", delayMs, reconnectAttempt)
        handler.postDelayed({
            reconnectPending = false
            if (!stopped && !isFinishing && !isDestroyed) preparePlayer()
        }, delayMs)
    }

    private fun delayFor(attempt: Int): Long = when {
        attempt <= 1 -> 1_000L
        attempt == 2 -> 2_000L
        attempt == 3 -> 4_000L
        attempt == 4 -> 8_000L
        else -> 15_000L
    }

    /** Se o canal ficou tocando bastante antes de cair, recomeca o backoff. */
    private fun resetBackoffIfStable() {
        if (lastReadyAt > 0L && SystemClock.elapsedRealtime() - lastReadyAt >= STABLE_PLAYBACK_MS) {
            reconnectAttempt = 0
        }
    }

    private fun showReconnecting(attempt: Int) {
        if (attempt < SHOW_ERROR_AFTER) {
            binding.reconnectText.visibility = View.VISIBLE
            binding.reconnectText.text = getString(R.string.reconnecting_attempt, attempt)
        } else {
            binding.reconnectText.visibility = View.GONE
        }
    }

    private fun hideReconnecting() {
        binding.reconnectText.visibility = View.GONE
    }

    private fun showError(detail: String) {
        binding.errorContainer.visibility = View.VISIBLE
        binding.errorText.text = getString(R.string.player_error_detail, streamUrl, detail)
    }

    private fun hideError() {
        binding.errorContainer.visibility = View.GONE
    }

    private fun releasePlayer() {
        handler.removeCallbacksAndMessages(null)
        reconnectPending = false
        binding.playerView.player = null
        player?.release()
        player = null
    }

    private fun hideSystemBars() {
        WindowCompat.setDecorFitsSystemWindows(window, false)
        val controller = WindowInsetsControllerCompat(window, binding.root)
        controller.hide(WindowInsetsCompat.Type.systemBars())
        controller.systemBarsBehavior =
            WindowInsetsControllerCompat.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
    }

    override fun onWindowFocusChanged(hasFocus: Boolean) {
        super.onWindowFocusChanged(hasFocus)
        if (hasFocus) hideSystemBars()
    }

    override fun onDestroy() {
        stopped = true
        releasePlayer()
        super.onDestroy()
    }

    companion object {
        private const val STABLE_PLAYBACK_MS = 30_000L
        private const val SHOW_ERROR_AFTER = 5

        const val EXTRA_URL = "extra_url"
        const val EXTRA_NAME = "extra_name"
        const val EXTRA_LOGO = "extra_logo"
        const val EXTRA_USER_AGENT = "extra_user_agent"
        const val EXTRA_REFERER = "extra_referer"
    }
}
