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
import androidx.lifecycle.lifecycleScope
import androidx.media3.common.AudioAttributes
import androidx.media3.common.MediaItem
import androidx.media3.common.MediaMetadata
import androidx.media3.common.PlaybackException
import androidx.media3.common.Player
import androidx.media3.common.Timeline
import androidx.media3.common.util.UnstableApi
import androidx.media3.datasource.DefaultHttpDataSource
import androidx.media3.exoplayer.DefaultLoadControl
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.exoplayer.source.DefaultMediaSourceFactory
import androidx.media3.exoplayer.upstream.DefaultLoadErrorHandlingPolicy
import com.eftv.android.data.CatalogStore
import com.eftv.android.data.ChannelKind
import com.eftv.android.databinding.ActivityPlayerBinding
import com.google.android.material.slider.Slider
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import timber.log.Timber
import java.util.concurrent.TimeUnit

/**
 * Player de um canal. Como transmissao ao vivo de IPTV costuma ser encerrada
 * pelo servidor depois de alguns segundos (ou sofrer queda de rede), o player
 * se reconecta sozinho e volta para o ponto ao vivo, sem parar no fim do stream.
 *
 * Para conteudo sob demanda (VOD) exibe progresso: quantos minutos ja assistiu
 * e quantos faltam, estilo Netflix/Amazon Prime.
 *
 * Ao iniciar a reproducao, o nome do canal e o badge "AO VIVO" somem automaticamente
 * depois de alguns segundos para nao atrapalhar a visao do conteúdo.
 */
class PlayerActivity : AppCompatActivity() {

    private lateinit var binding: ActivityPlayerBinding
    private var player: ExoPlayer? = null

    private lateinit var streamUrl: String
    private var channelName: String = ""
    private var channelLogo: String = ""
    private var userAgent: String = PlaylistConfig.USER_AGENT
    private var referer: String? = null
    private var channelKind: ChannelKind = ChannelKind.LIVE

    /** Posicao salva para retomar um filme/serie. */
    private var savedPositionMs = 0L
    private var resumeApplied = false
    private var lastProgressSaveAt = 0L

    private val catalog by lazy { CatalogStore.get(this) }

    /** Se o conteudo atual e ao vivo (true) ou sob demanda (false). */
    private var isLive = false

    private val handler = Handler(Looper.getMainLooper())
    private var reconnectAttempt = 0
    private var reconnectPending = false
    private var lastReadyAt = 0L
    private var lastErrorDetail: String? = null
    private var stopped = false
    private var softRecoveryAttempts = 0

    /** Job/Callback para atualizar o progresso do VOD periodicamente. */
    private var vodProgressCallback: Runnable? = null

    /** Callback para esconder o overlay (nome, badges, controles) apos o delay. */
    private var hideOverlayCallback: Runnable? = null

    /** Se o overlay (topBar + bottomControls) esta visível no momento. */
    private var overlayVisible = false

    /** Evita que a barra de progresso "pule" enquanto o usuario arrasta. */
    private var userSeeking = false

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
        channelKind = intent.getStringExtra(EXTRA_KIND)
            ?.let { runCatching { ChannelKind.valueOf(it) }.getOrNull() }
            ?: ChannelKind.LIVE

        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        volumeControlStream = AudioManager.STREAM_MUSIC
        hideSystemBars()

        binding.playerChannelName.text = channelName
        if (channelName.isBlank()) binding.playerChannelName.visibility = View.GONE
        binding.closeButton.setOnClickListener { finish() }
        binding.retryButton.setOnClickListener { startPlayback() }
        binding.backButton.setOnClickListener { finish() }

        // Inicialmente o progresso VOD fica escondido
        binding.vodProgressText.visibility = View.GONE

        // Toque na tela alterna a visibilidade do overlay (topBar + controles)
        binding.touchLayer.setOnClickListener { toggleOverlay() }

        binding.btnPlayPause.setOnClickListener { togglePlayPause() }
        binding.btnRewind.setOnClickListener { seekBy(-SEEK_STEP_MS) }
        binding.btnForward.setOnClickListener { seekBy(SEEK_STEP_MS) }

        // Barra de progresso: procura ao soltar o dedo (estilo Netflix/Prime)
        binding.progressSlider.addOnSliderTouchListener(object : Slider.OnSliderTouchListener {
            override fun onStartTrackingTouch(slider: Slider) {
                userSeeking = true
            }

            override fun onStopTrackingTouch(slider: Slider) {
                userSeeking = false
                val current = player ?: return
                val duration = current.duration
                if (duration > 0) {
                    current.seekTo((slider.value / 100f * duration).toLong())
                }
                updatePlaybackUi()
                scheduleHideOverlay()
            }
        })
    }

    override fun onStart() {
        super.onStart()
        stopped = false
        if (::binding.isInitialized && this::streamUrl.isInitialized && !isFinishing && !isDestroyed) {
            // Sempre (re)comeca do ponto ao vivo ao abrir/voltar para a tela.
            startPlayback()
        }
    }

    override fun onPause() {
        super.onPause()
        // Pausa o player quando sai da tela ou coloca o app em background.
        // Isso evita que o audio/video continue rodando e trave o app.
        player?.let { current ->
            current.playWhenReady = false
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
        // Nao inicia playback se a activity ja esta sendo encerrada.
        if (isFinishing || isDestroyed) return

        reconnectAttempt = 0
        softRecoveryAttempts = 0
        lastReadyAt = 0L
        lastErrorDetail = null
        isLive = channelKind == ChannelKind.LIVE
        lastProgressSaveAt = 0L
        hideError()
        hideReconnecting()
        cancelVodProgress()
        cancelHideOverlay()
        preparePlayer()
    }

    @androidx.annotation.OptIn(UnstableApi::class)
    private fun preparePlayer() {
        releasePlayer()

        if (channelKind != ChannelKind.LIVE) {
            savedPositionMs = runCatching { catalog.progress(streamUrl)?.positionMs ?: 0L }
                .getOrDefault(0L)
            resumeApplied = false
        }

        val httpFactory = DefaultHttpDataSource.Factory()
            .setUserAgent(userAgent)
            .setConnectTimeoutMs(15_000)
            .setReadTimeoutMs(20_000)
            .setAllowCrossProtocolRedirects(true)

        referer?.takeIf { it.isNotBlank() }?.let { value ->
            httpFactory.setDefaultRequestProperties(mapOf("Referer" to value))
        }

        val loadControl = DefaultLoadControl.Builder()
            // Buffer folgado: absorve oscilacao de rede sem parar a imagem.
            .setBufferDurationsMs(
                MIN_BUFFER_MS,
                MAX_BUFFER_MS,
                BUFFER_FOR_PLAYBACK_MS,
                BUFFER_FOR_PLAYBACK_AFTER_REBUFFER_MS,
            )
            .setPrioritizeTimeOverSizeThresholds(true)
            .build()

        val mediaSourceFactory = DefaultMediaSourceFactory(this)
            .setDataSourceFactory(httpFactory)
            // Mais tentativas internas antes de reportar erro ao player.
            .setLoadErrorHandlingPolicy(DefaultLoadErrorHandlingPolicy(MAX_LOAD_RETRIES))

        val exoPlayer = ExoPlayer.Builder(this)
            .setMediaSourceFactory(mediaSourceFactory)
            .setLoadControl(loadControl)
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
                // Falha de rede costuma ser passageira: tenta religar no mesmo
                // player antes de recriar tudo (evita o "pisca" de recarga).
                if (shouldRecoverInPlace(error)) {
                    softRecoveryAttempts++
                    Timber.i("Recuperacao suave (%d)", softRecoveryAttempts)
                    resumeFromDefaultPosition()
                } else {
                    scheduleReconnect()
                }
            }

            override fun onPlaybackStateChanged(playbackState: Int) {
                when (playbackState) {
                    Player.STATE_IDLE -> {
                        // Aguardando prepare/reconexao; nada a fazer aqui.
                    }

                    Player.STATE_BUFFERING -> {
                        // Travadinha momentanea: o proprio ExoPlayer reabastece.
                        Timber.d("Buffering em %d ms", player?.bufferedPosition)
                    }

                    Player.STATE_READY -> {
                        resetBackoffIfStable()
                        lastReadyAt = SystemClock.elapsedRealtime()
                        hideError()
                        hideReconnecting()

                        // Detecta se e ao vivo ou sob demanda. O tipo vindo
                        // do catalogo tem prioridade para canais ao vivo.
                        isLive = channelKind == ChannelKind.LIVE ||
                            exoPlayer.isCurrentMediaItemLive
                        updateLiveBadge()

                        if (!isLive && !resumeApplied) {
                            val duration = exoPlayer.duration
                            if (duration > 0) {
                                if (savedPositionMs > RESUME_MIN_MS &&
                                    savedPositionMs < duration - RESUME_END_GUARD_MS
                                ) {
                                    exoPlayer.seekTo(savedPositionMs)
                                }
                                resumeApplied = true
                                savedPositionMs = 0L
                            }
                        }

                        // Para TODOS os conteudos (ao vivo e VOD): mostra o overlay
                        // por 3 segundos, depois esconde para ficar so o conteudo
                        binding.playerChannelName.visibility = View.VISIBLE
                        binding.liveBadge.visibility = if (isLive) View.VISIBLE else View.GONE
                        binding.qualityBadgePlayer.visibility = View.VISIBLE

                        // Atualiza os controles de acordo com o tipo de conteudo
                        startUiUpdates()
                        updatePlaybackUi()

                        // Mostra o overlay (topBar + controles) e agenda o escondimento apos 3s
                        showOverlay()
                        scheduleHideOverlay()
                    }

                    Player.STATE_ENDED -> {
                        if (channelKind == ChannelKind.LIVE || isLive) {
                            // Muitos servidores IPTV fecham o stream depois de N segundos.
                            lastErrorDetail = getString(R.string.stream_ended_by_server)
                            // Retoma sem recriar o player (evita o recarregamento visivel).
                            resumeFromDefaultPosition()
                        } else {
                            // VOD: salva (ou limpa, se chegou ao fim) e para.
                            val duration = exoPlayer.duration
                            val position = exoPlayer.currentPosition
                            if (duration > 0 && duration - position <= RESUME_END_GUARD_MS) {
                                persistProgress(position, duration, clear = true)
                            } else {
                                persistProgress(position, duration)
                            }
                            updatePlaybackUi()
                            showOverlay()
                            scheduleHideOverlay()
                        }
                    }
                }
            }

            override fun onTimelineChanged(timeline: Timeline, reason: Int) {
                updateLiveBadge()
            }
        })

        binding.playerView.player = exoPlayer
        exoPlayer.setMediaItem(
            MediaItem.Builder()
                .setUri(streamUrl)
                .setMediaMetadata(metadata)
                .setLiveConfiguration(
                    MediaItem.LiveConfiguration.Builder()
                        .setTargetOffsetMs(LIVE_TARGET_OFFSET_MS)
                        .build()
                )
                .build()
        )
        exoPlayer.prepare()
        exoPlayer.playWhenReady = true
        player = exoPlayer
        updateLiveBadge()
    }

    private fun updateLiveBadge() {
        binding.liveBadge.visibility =
            if (isLive || player?.isCurrentMediaItemLive == true) View.VISIBLE else View.GONE
    }

    /**
     * Inicia as atualizacoes periodicas da interface do player:
     * botao play/pause, barra de progresso e texto "Assistido/Restam" (VOD).
     */
    private fun startUiUpdates() {
        cancelVodProgress()
        vodProgressCallback = object : Runnable {
            override fun run() {
                updatePlaybackUi()
                if (!stopped && !isFinishing && !isDestroyed) {
                    handler.postDelayed(this, UI_TICK_MS)
                }
            }
        }
        handler.post(vodProgressCallback!!)
    }

    private fun cancelVodProgress() {
        vodProgressCallback?.let { handler.removeCallbacks(it) }
        vodProgressCallback = null
    }

    /**
     * Salva o progresso do VOD em segundo plano. Com clear = true remove o
     * progresso quando o filme/episodio chega ao fim.
     */
    private fun persistProgress(positionMs: Long, durationMs: Long, clear: Boolean = false) {
        if (channelKind == ChannelKind.LIVE || durationMs <= 0) return
        lifecycleScope.launch(Dispatchers.IO) {
            runCatching {
                if (clear) {
                    catalog.clearProgress(streamUrl)
                } else {
                    catalog.saveProgress(streamUrl, positionMs.coerceAtLeast(0), durationMs)
                }
            }
        }
    }

    /** Salva de forma sincrona ao sair, antes de destruir o player. */
    private fun saveCurrentProgress() {
        val current = player ?: return
        if (channelKind == ChannelKind.LIVE) return
        val duration = current.duration
        if (duration <= 0) return
        runCatching {
            catalog.saveProgress(
                streamUrl,
                current.currentPosition.coerceAtLeast(0),
                duration,
            )
        }
    }

    /** Atualiza botao play/pause e, para VOD, barra e tempos assistido/restante. */
    private fun updatePlaybackUi() {
        val current = player ?: return

        val playing = current.isPlaying
        binding.btnPlayPause.setImageResource(
            if (playing) R.drawable.ic_pause else R.drawable.ic_play,
        )
        binding.btnPlayPause.contentDescription =
            getString(if (playing) R.string.player_pause else R.string.player_play)

        // Ao vivo nao tem linha do tempo: mostra so play/pause.
        if (isLive) {
            binding.vodProgressText.visibility = View.GONE
            binding.positionText.visibility = View.GONE
            binding.durationText.visibility = View.GONE
            binding.progressSlider.visibility = View.GONE
            binding.btnRewind.visibility = View.GONE
            binding.btnForward.visibility = View.GONE
            return
        }

        binding.positionText.visibility = View.VISIBLE
        binding.durationText.visibility = View.VISIBLE
        binding.progressSlider.visibility = View.VISIBLE
        binding.btnRewind.visibility = View.VISIBLE
        binding.btnForward.visibility = View.VISIBLE

        val durationMs = current.duration
        val positionMs = current.currentPosition.coerceAtLeast(0)

        binding.positionText.text = formatClock(positionMs)

        if (durationMs <= 0) {
            binding.durationText.text = "--:--"
            binding.vodProgressText.text =
                "Assistido: ${formatTime(positionMs)} · Restam: --"
            binding.progressSlider.value = 0f
        } else {
            binding.durationText.text = formatClock(durationMs)
            if (!userSeeking) {
                binding.progressSlider.value =
                    (positionMs.toFloat() / durationMs * 100f).coerceIn(0f, 100f)
            }
            val remainingMs = (durationMs - positionMs).coerceAtLeast(0)
            binding.vodProgressText.text =
                "Assistido: ${formatTime(positionMs)} · Restam: ${formatTime(remainingMs)}"

            // Guarda a posicao a cada poucos segundos para retomar depois.
            val now = SystemClock.elapsedRealtime()
            if (now - lastProgressSaveAt >= PROGRESS_SAVE_INTERVAL_MS) {
                lastProgressSaveAt = now
                persistProgress(positionMs, durationMs)
            }
        }
        binding.vodProgressText.visibility = View.VISIBLE
    }

    /** Play/pause pelo botao central. */
    private fun togglePlayPause() {
        val current = player ?: return
        if (current.isPlaying) current.pause() else current.play()
        updatePlaybackUi()
        scheduleHideOverlay()
    }

    /** Avanca/retrocede (apenas VOD; ao vivo fica sempre no ponto ao vivo). */
    private fun seekBy(deltaMs: Long) {
        val current = player ?: return
        if (isLive) return

        val durationMs = current.duration
        var target = current.currentPosition + deltaMs
        if (target < 0) target = 0
        if (durationMs > 0 && target > durationMs) target = durationMs

        current.seekTo(target)
        updatePlaybackUi()
        scheduleHideOverlay()
    }

    /** Formata milissegundos como mm:ss ou hh:mm:ss (usado nos tempos do player). */
    private fun formatClock(ms: Long): String {
        val totalSeconds = TimeUnit.MILLISECONDS.toSeconds(ms.coerceAtLeast(0))
        val hours = totalSeconds / 3600
        val minutes = (totalSeconds % 3600) / 60
        val seconds = totalSeconds % 60
        return if (hours > 0) {
            "%d:%02d:%02d".format(hours, minutes, seconds)
        } else {
            "%02d:%02d".format(minutes, seconds)
        }
    }

    /** Formata milissegundos em "X min" ou "X:XX" se menor que 1 hora. */
    private fun formatTime(ms: Long): String {
        val totalSeconds = TimeUnit.MILLISECONDS.toSeconds(ms.coerceAtLeast(0))
        val minutes = totalSeconds / 60
        val seconds = totalSeconds % 60
        return if (minutes >= 60) {
            val hours = minutes / 60
            val remainingMin = minutes % 60
            "${hours}h ${remainingMin}min"
        } else if (minutes > 0) {
            "${minutes}min ${String.format("%02d", seconds)}s"
        } else {
            "${seconds}s"
        }
    }

    /**
     * Mostra o overlay completo: topBar (nome, badge ao vivo, qualidade, fechar)
     * e bottomControls (play/pause, avançar, retroceder, progresso).
     */
    private fun showOverlay() {
        cancelHideOverlay()
        overlayVisible = true
        Timber.d("Overlay visivel (nome/badges/controles)")
        binding.topBar.visibility = View.VISIBLE
        binding.bottomControls.visibility = View.VISIBLE
    }

    /**
     * Esconde o overlay completo: topBar e bottomControls.
     * Fica apenas o conteudo passando na tela (estilo Netflix/Prime).
     */
    private fun hideOverlay() {
        cancelHideOverlay()
        overlayVisible = false
        Timber.d("Overlay oculto (apenas video)")
        binding.topBar.visibility = View.GONE
        binding.bottomControls.visibility = View.GONE
    }

    /** Alterna a visibilidade do overlay ao tocar na tela. */
    private fun toggleOverlay() {
        if (overlayVisible) {
            hideOverlay()
        } else {
            showOverlay()
            // Reagenda o escondimento automatico apos 3 segundos
            scheduleHideOverlay()
        }
    }

    /**
     * Agenda o escondimento do overlay apos um delay,
     * para nao atrapalhar a visao do conteudo (estilo Netflix/Prime).
     */
    private fun scheduleHideOverlay() {
        cancelHideOverlay()
        hideOverlayCallback = object : Runnable {
            override fun run() {
                hideOverlay()
            }
        }
        handler.postDelayed(hideOverlayCallback!!, HIDE_OVERLAY_DELAY_MS)
    }

    private fun cancelHideOverlay() {
        hideOverlayCallback?.let { handler.removeCallbacks(it) }
        hideOverlayCallback = null
    }

    /**
     * Volta ao ponto padrao (ao vivo) usando o mesmo player. Sem release e sem
     * trocar a surface, o canal continua sem o "pisca" de recarregamento.
     */
    private fun resumeFromDefaultPosition() {
        if (stopped) return
        val current = player ?: run {
            scheduleReconnect()
            return
        }

        hideError()
        hideReconnecting()
        if (channelKind != ChannelKind.LIVE && !isLive) {
            val saved = runCatching { catalog.progress(streamUrl)?.positionMs }.getOrNull() ?: 0L
            val target = if (saved > 0) saved else current.currentPosition.coerceAtLeast(0)
            current.seekTo(target)
        } else {
            current.seekToDefaultPosition()
        }
        current.prepare()
        current.playWhenReady = true

        // Se nao voltar sozinho, cai na reconexao completa.
        handler.postDelayed({
            if (!stopped && player === current &&
                current.playbackState != Player.STATE_READY && !current.isPlaying
            ) {
                scheduleReconnect()
            }
        }, RESUME_TIMEOUT_MS)
    }

    /**
     * Erros de rede/IO depois de o canal ja estar tocando costumam ser
     * passageiros: religar no mesmo player e mais rapido e nao pisca a tela.
     */
    private fun shouldRecoverInPlace(error: PlaybackException): Boolean {
        if (softRecoveryAttempts >= MAX_SOFT_RECOVERIES) return false
        if (lastReadyAt == 0L) return false
        return when (error.errorCode) {
            PlaybackException.ERROR_CODE_IO_UNSPECIFIED,
            PlaybackException.ERROR_CODE_IO_NETWORK_CONNECTION_FAILED,
            PlaybackException.ERROR_CODE_IO_NETWORK_CONNECTION_TIMEOUT,
            PlaybackException.ERROR_CODE_IO_READ_POSITION_OUT_OF_RANGE,
            -> true

            else -> false
        }
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
            softRecoveryAttempts = 0
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
        saveCurrentProgress()
        handler.removeCallbacksAndMessages(null)
        cancelVodProgress()
        cancelHideOverlay()
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
        private const val RESUME_TIMEOUT_MS = 7_000L
        private const val LIVE_TARGET_OFFSET_MS = 8_000L

        /** Delay para esconder nome/badges apos o conteudo comecar a tocar (ms). */
        private const val HIDE_OVERLAY_DELAY_MS = 3000L

        /** Intervalo de atualizacao dos controles do player (ms). */
        private const val UI_TICK_MS = 500L

        /** Quanto os botoes de avancar/retroceder pulam (ms). */
        private const val SEEK_STEP_MS = 10_000L

        // Buffer: segura mais alguns segundos para atravessar oscilacao de rede.
        private const val MIN_BUFFER_MS = 15_000
        private const val MAX_BUFFER_MS = 40_000
        private const val BUFFER_FOR_PLAYBACK_MS = 1_500
        private const val BUFFER_FOR_PLAYBACK_AFTER_REBUFFER_MS = 3_000
        private const val MAX_LOAD_RETRIES = 6
        private const val MAX_SOFT_RECOVERIES = 2

        /** Nao retoma se o progresso salvo estiver no comeco/fim demais. */
        private const val RESUME_MIN_MS = 5_000L
        private const val RESUME_END_GUARD_MS = 10_000L

        /** Intervalo para gravar a posicao do VOD (ms). */
        private const val PROGRESS_SAVE_INTERVAL_MS = 5_000L

        const val EXTRA_URL = "extra_url"
        const val EXTRA_NAME = "extra_name"
        const val EXTRA_LOGO = "extra_logo"
        const val EXTRA_USER_AGENT = "extra_user_agent"
        const val EXTRA_REFERER = "extra_referer"
        const val EXTRA_KIND = "extra_kind"
    }
}
