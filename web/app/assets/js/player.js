/* ============================================================
   EFTV — Player web/PWA
   HLS (hls.js), MPEG-TS (mpegts.js), DASH (dash.js) e MP4.
   Inclui: faixas de áudio/qualidade/legenda, ao vivo, retry,
   heartbeat de sessão e salvamento de progresso.
   ============================================================ */

(() => {
  "use strict";

  const BIBLIOTECAS = {
    "hls.min.js": {
      url: "https://cdn.jsdelivr.net/npm/hls.js@1.5.17/dist/hls.min.js",
    },
    "mpegts.js": {
      url: "https://cdn.jsdelivr.net/npm/mpegts.js@1.7.3/dist/mpegts.min.js",
    },
    "dash.all.min.js": {
      url: "https://cdn.jsdelivr.net/npm/dashjs@5.3.0/dist/modern/umd/dash.all.min.js",
    },
  };

  const carregadas = {};

  function carregarBiblioteca(nome) {
    if (carregadas[nome]) return carregadas[nome];
    const info = BIBLIOTECAS[nome];
    carregadas[nome] = new Promise((resolver, rejeitar) => {
      const script = document.createElement("script");
      script.src = info.url;
      script.crossOrigin = "anonymous";
      script.async = true;
      script.onload = () => resolver();
      script.onerror = () => rejeitar(new Error("Falha ao carregar " + nome));
      document.head.appendChild(script);
    });
    return carregadas[nome];
  }

  class PlayerError extends Error {
    constructor(msg, tipo) {
      super(msg);
      this.name = "PlayerError";
      this.tipo = tipo || "geral";
    }
  }

  const player = {
    video: null,
    hls: null,
    dashPlayer: null,
    tsPlayer: null,
    _listeners: new Set(),
    _aoVivo: false,
    _tentativas: 0,
    _maxTentativas: 6,
    _heartbeatTimer: null,
    _progressTimer: null,
    _sessaoId: null,
    _itemAtual: null,
    _ultimoProgresso: 0,

    subscribe(fn) {
      this._listeners.add(fn);
      return () => this._listeners.delete(fn);
    },

    _notify(evento, dado) {
      this._listeners.forEach((fn) => {
        try { fn(evento, dado); } catch (_) {}
      });
    },

    init(videoElement) {
      if (this.video === videoElement) return;
      this.video = videoElement;
      this._vincularEventos();
    },

    _vincularEventos() {
      const v = this.video;
      if (!v || v.dataset.eftvEventos === "1") return;
      v.dataset.eftvEventos = "1";

      ["loadstart", "loadeddata", "canplay", "play", "pause", "waiting", "playing", "ended", "seeked"]
        .forEach((evento) => {
          v.addEventListener(evento, () => this._notify(evento));
        });

      v.addEventListener("error", () => {
        this._notify("error", new PlayerError("Falha ao carregar o vídeo.", "video"));
      });

      v.addEventListener("timeupdate", () => {
        if (!this._itemAtual) return;
        const dur = v.duration || 0;
        const atual = v.currentTime || 0;
        if (!Number.isFinite(dur) || dur <= 0) return;
        const progresso = Math.min(100, Math.max(0, (atual / dur) * 100));
        // Não salva nos primeiros 5s nem nos últimos 10s (igual ao Android)
        if (atual < 5 || dur - atual < 10) return;
        if (Math.abs(progresso - this._ultimoProgresso) >= 1) {
          this._ultimoProgresso = progresso;
          this._notify("progress", { progresso, atual, duracao: dur, item: this._itemAtual });
        }
      });
    },

    async carregar(item, opcoes = {}) {
      const { url, tipo = "hls", token = null } = opcoes;
      this._itemAtual = item;
      this._aoVivo = !!item.aoVivo;
      this._tentativas = 0;
      this._atualizarMediaSession(item);

      if (!url) {
        this._notify("error", new PlayerError("Este canal não possui URL de transmissão configurada.", "sem-url"));
        return;
      }

      try {
        switch (tipo) {
          case "hls": await this._loadHls(url, token); break;
          case "dash": await this._loadDash(url, token); break;
          case "ts": await this._loadTs(url, token); break;
          case "mp4": this._loadMp4(url); break;
          default: throw new PlayerError("Tipo de stream não suportado: " + tipo, "tipo");
        }
      } catch (erro) {
        this._notify("error", erro);
        throw erro;
      }
    },

    async _loadHls(url, token) {
      const video = this.video;

      if (!window.Hls && video.canPlayType("application/vnd.apple.mpegurl")) {
        video.src = url;
        video.load();
        return new Promise((resolve) => {
          video.addEventListener("loadedmetadata", () => {
            this._notify("ready");
            resolve();
          }, { once: true });
        });
      }

      if (!window.Hls) await carregarBiblioteca("hls.min.js");

      this._destruirHls();
      this.hls = new window.Hls({
        enableWorker: true,
        lowLatencyMode: this._aoVivo,
        liveDurationInfinity: this._aoVivo,
        backBufferLength: 30,
        maxBufferLength: 30,
        // Envia o token de sessão em todas as requisições do manifesto/segmentos.
        xhrSetup: token
          ? (xhr) => {
              try { xhr.setRequestHeader("Authorization", "Bearer " + token); } catch (_) {}
            }
          : undefined,
      });

      this.hls.loadSource(url);
      this.hls.attachMedia(video);

      return new Promise((resolve, reject) => {
        let resolvido = false;

        this.hls.on(window.Hls.Events.MANIFEST_PARSED, () => {
          resolvido = true;
          this._notify("ready");
          resolve();
        });

        this.hls.on(window.Hls.Events.LEVEL_LOADED, (_e, data) => {
          if (data && data.details && data.details.live) this._notify("live");
        });

        this.hls.on(window.Hls.Events.ERROR, (_e, data) => {
          if (!data.fatal) return;

          // Reconexão automática (equivalente ao retry do ExoPlayer no Android).
          if (this._tentativas < this._maxTentativas) {
            this._tentativas += 1;
            const atraso = Math.min(8000, 1000 * this._tentativas);
            this._notify("reconectando", { tentativa: this._tentativas, atraso });

            setTimeout(() => {
              if (!this.hls) return;
              try {
                if (data.type === window.Hls.ErrorTypes.MEDIA_ERROR) {
                  this.hls.recoverMediaError();
                } else {
                  this.hls.startLoad();
                }
              } catch (_) {}
            }, atraso);
            return;
          }

          const err = new PlayerError(
            "Não foi possível carregar a transmissão (" + data.details + ").",
            "hls"
          );
          this._notify("error", err);
          if (!resolvido) reject(err);
        });
      });
    },

    async _loadDash(url, token) {
      if (!window.dashjs) await carregarBiblioteca("dash.all.min.js");
      this._destruirDash();
      this.dashPlayer = window.dashjs.MediaPlayer().create();
      this.dashPlayer.initialize(this.video, url, false);

      if (token) {
        this.dashPlayer.setProtectionData({
          "com.widevine.alpha": {
            serverURL: "",
            httpRequestHeaders: { Authorization: "Bearer " + token },
          },
        });
      }

      return new Promise((resolve, reject) => {
        this.dashPlayer.on(window.dashjs.MediaPlayer.events.STREAM_INITIALIZED, () => {
          this._notify("ready");
          resolve();
        });
        this.dashPlayer.on(window.dashjs.MediaPlayer.events.ERROR, (e) => {
          const err = new PlayerError("Erro DASH: " + (e.error?.message || e), "dash");
          this._notify("error", err);
          reject(err);
        });
      });
    },

    async _loadTs(url, token) {
      if (!window.mpegts || typeof window.mpegts.createPlayer !== "function") {
        await carregarBiblioteca("mpegts.js");
      }
      this._destruirTs();
      this.tsPlayer = window.mpegts.createPlayer(
        { type: "mse", isLive: true, url },
        { enableWorker: true, liveBufferLatencyChasing: true }
      );
      this.tsPlayer.attachMediaElement(this.video);
      this.tsPlayer.load();

      return new Promise((resolve, reject) => {
        this.tsPlayer.on(window.mpegts.Events.LOADED_METADATA, () => {
          this._notify("ready");
          resolve();
        });
        this.tsPlayer.on(window.mpegts.Events.ERROR, (_t, detalhe) => {
          const err = new PlayerError("Erro MPEG-TS: " + detalhe, "ts");
          this._notify("error", err);
          reject(err);
        });
      });
    },

    _loadMp4(url) {
      this.video.src = url;
      this.video.load();
      return Promise.resolve();
    },

    // ---------- Controles ----------
    play() {
      if (!this.video) return Promise.reject(new PlayerError("Vídeo não iniciado"));
      return this.video.play();
    },
    pause() { if (this.video) this.video.pause(); },
    toggle() { return this.video && this.video.paused ? this.play() : this.pause(); },

    stop() {
      this._pararHeartbeat();
      this._pararProgresso();
      this._limparMediaSession();
      if (this.video) {
        this.video.pause();
        this.video.removeAttribute("src");
        this.video.load();
      }
      this._destruirHls();
      this._destruirDash();
      this._destruirTs();
      this._itemAtual = null;
      this._aoVivo = false;
    },

    seek(tempo) { if (this.video) this.video.currentTime = tempo; },

    seekRelativo(delta) {
      if (!this.video) return;
      const alvo = (this.video.currentTime || 0) + delta;
      const max = Number.isFinite(this.video.duration) ? this.video.duration : alvo;
      this.video.currentTime = Math.min(Math.max(0, alvo), max);
    },

    setVolume(v) { if (this.video) this.video.volume = Math.max(0, Math.min(1, v)); },
    setMuted(m) { if (this.video) this.video.muted = m; },
    toggleMute() { if (this.video) this.video.muted = !this.video.muted; return this.video.muted; },

    toggleFullscreen() {
      if (!this.video) return;
      if (document.fullscreenElement) document.exitFullscreen();
      else if (this.video.requestFullscreen) this.video.requestFullscreen();
      else if (this.video.webkitRequestFullscreen) this.video.webkitRequestFullscreen();
    },

    async togglePiP() {
      if (!this.video) return false;
      try {
        if (document.pictureInPictureElement) {
          await document.exitPictureInPicture();
          return false;
        }
        await this.video.requestPictureInPicture();
        return true;
      } catch (_) {
        return false;
      }
    },

    isPlaying() { return this.video && !this.video.paused && !this.video.ended; },
    getCurrentTime() { return this.video ? this.video.currentTime : 0; },
    getDuration() { return this.video ? this.video.duration : 0; },

    irParaAoVivo() {
      const v = this.video;
      if (!v) return;
      if (this.hls && Number.isFinite(this.hls.liveSyncPosition)) {
        try {
          v.currentTime = this.hls.liveSyncPosition;
          v.play().catch(() => {});
          return;
        } catch (_) {}
      }
      if (this.tsPlayer) {
        this._destruirTs();
        this._loadTs(v.currentSrc || v.src);
        return;
      }
      const faixas = v.seekable;
      if (faixas && faixas.length) {
        try { v.currentTime = Math.max(0, faixas.end(faixas.length - 1) - 0.5); } catch (_) {}
      }
      v.play().catch(() => {});
    },

    // ---------- Faixas (qualidade / áudio / legenda) ----------
    faixas() {
      const resultado = { qualidade: [], audio: [], legenda: [] };

      if (this.hls) {
        resultado.qualidade = (this.hls.levels || []).map((nivel, i) => ({
          id: i,
          rotulo: nivel.height ? nivel.height + "p" : (nivel.name || "Nível " + (i + 1)),
          ativo: this.hls.currentLevel === i,
        }));
        if (this.hls.audioTracks) {
          resultado.audio = this.hls.audioTracks.map((t, i) => ({
            id: i, rotulo: t.name || t.lang || "Áudio " + (i + 1), ativo: this.hls.audioTrack === i,
          }));
        }
        if (this.hls.subtitleTracks) {
          resultado.legenda = this.hls.subtitleTracks.map((t, i) => ({
            id: i, rotulo: t.name || t.lang || "Legenda " + (i + 1), ativo: this.hls.subtitleTrack === i,
          }));
        }
      }

      if (this.dashPlayer) {
        try {
          const lista = this.dashPlayer.getBitrateInfoListFor("video") || [];
          resultado.qualidade = lista.map((q, i) => ({
            id: i, rotulo: (q.height ? q.height + "p" : Math.round(q.bitrate / 1000) + " kbps"), ativo: false,
          }));
        } catch (_) {}
      }

      if (this.video && this.video.audioTracks) {
        resultado.audio = [...this.video.audioTracks].map((t, i) => ({
          id: i, rotulo: t.label || t.language || "Áudio " + (i + 1), ativo: t.enabled,
        }));
      }
      if (this.video && this.video.textTracks) {
        resultado.legenda = [...this.video.textTracks].map((t, i) => ({
          id: i, rotulo: t.label || t.language || "Legenda " + (i + 1), ativo: t.mode === "showing",
        }));
      }
      return resultado;
    },

    selecionarQualidade(id) {
      if (this.hls) this.hls.currentLevel = Number(id);
      if (this.dashPlayer) {
        try { this.dashPlayer.setQualityFor("video", Number(id), true); } catch (_) {}
      }
    },

    selecionarAudio(id) {
      if (this.hls && this.hls.audioTracks) this.hls.audioTrack = Number(id);
      if (this.video && this.video.audioTracks) {
        [...this.video.audioTracks].forEach((t, i) => { t.enabled = i === Number(id); });
      }
    },

    selecionarLegenda(id) {
      if (this.hls) this.hls.subtitleTrack = Number(id);
      if (this.video && this.video.textTracks) {
        [...this.video.textTracks].forEach((t, i) => {
          t.mode = i === Number(id) ? "showing" : "disabled";
        });
      }
    },

    // ---------- Sessão / heartbeat ----------
    iniciarSessao(sessionId) {
      this._sessaoId = sessionId;
      this._pararHeartbeat();
      if (!sessionId) return;
      this._heartbeatTimer = setInterval(async () => {
        try {
          await window.EFTV_API.heartbeatPlayer(this._sessaoId);
        } catch (erro) {
          if (erro.status === 409 || erro.status === 401 || erro.status === 403) {
            this._notify("sessao-encerrada", erro);
            this.pause();
          }
        }
      }, window.EFTV_CONFIG.HEARTBEAT_MS);
    },

    async encerrarSessao() {
      const id = this._sessaoId;
      this._sessaoId = null;
      this._pararHeartbeat();
      if (id) {
        try { await window.EFTV_API.pararPlayer(id); } catch (_) {}
      }
    },

    _pararHeartbeat() {
      if (this._heartbeatTimer) clearInterval(this._heartbeatTimer);
      this._heartbeatTimer = null;
    },

    _pararProgresso() {
      if (this._progressTimer) clearInterval(this._progressTimer);
      this._progressTimer = null;
    },

    // Controles na tela de bloqueio / central de mídia (Media Session API).
    _atualizarMediaSession(item) {
      if (!("mediaSession" in navigator)) return;
      try {
        if (typeof MediaMetadata !== "undefined") {
          navigator.mediaSession.metadata = new MediaMetadata({
            title: item.nome || "EFTV",
            artist: item.grupo || "EFTV",
            album: "EFTV",
            artwork: item.logo
              ? [{ src: item.logo, sizes: "512x512", type: "image/png" }]
              : [],
          });
        }
        const acoes = {
          play: () => this.play().catch(() => {}),
          pause: () => this.pause(),
          stop: () => this.stop(),
          seekbackward: (d) => this.seekRelativo(-(d.seekOffset || 10)),
          seekforward: (d) => this.seekRelativo(d.seekOffset || 10),
          seekto: (d) => {
            if (Number.isFinite(d.seekTime)) this.seek(d.seekTime);
          },
        };
        Object.entries(acoes).forEach(([acao, fn]) => {
          try { navigator.mediaSession.setActionHandler(acao, fn); } catch (_) {}
        });
      } catch (_) {}
    },

    _limparMediaSession() {
      if (!("mediaSession" in navigator)) return;
      try {
        navigator.mediaSession.metadata = null;
        ["play", "pause", "stop", "seekbackward", "seekforward", "seekto"].forEach((acao) => {
          try { navigator.mediaSession.setActionHandler(acao, null); } catch (_) {}
        });
      } catch (_) {}
    },

    _destruirHls() {
      if (this.hls) { try { this.hls.destroy(); } catch (_) {} this.hls = null; }
    },
    _destruirDash() {
      if (this.dashPlayer) { try { this.dashPlayer.reset(); } catch (_) {} this.dashPlayer = null; }
    },
    _destruirTs() {
      if (this.tsPlayer) { try { this.tsPlayer.destroy(); } catch (_) {} this.tsPlayer = null; }
    },
  };

  window.player = player;
  window.EFTV_PLAYER = player;
})();