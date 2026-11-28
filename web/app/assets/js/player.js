/* ============================================================
   EFTV — Player web/PWA
   HLS (hls.js), MPEG-TS (mpegts.js), DASH (dash.js) e MP4.
   Inclui: faixas de áudio/qualidade/legenda, ao vivo, retry com
   backoff, troca de fonte (direto ↔ proxy), Wake Lock, overscan,
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
    _fontes: [],
    _fonteIndice: 0,
    _fonteAtual: null,
    _token: null,
    _headers: null,
    _geracao: 0,
    _heartbeatTimer: null,
    _progressTimer: null,
    _sessaoId: null,
    _itemAtual: null,
    _ultimoProgresso: 0,
    _estavelTimer: null,
    _wakeLock: null,
    _visibilidadeLigada: false,

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
      if (!v) return;

      if (!this._visibilidadeLigada) {
        this._visibilidadeLigada = true;
        document.addEventListener("visibilitychange", () => {
          if (document.visibilityState === "visible" && this.isPlaying()) {
            this._solicitarWakeLock();
          } else {
            this._liberarWakeLock();
          }
        });
      }

      if (v.dataset.eftvEventos === "1") return;
      v.dataset.eftvEventos = "1";

      ["loadstart", "loadeddata", "canplay", "play", "pause", "waiting", "seeked"]
        .forEach((evento) => {
          v.addEventListener(evento, () => this._notify(evento));
        });

      v.addEventListener("playing", () => {
        this._notify("playing");
        this._solicitarWakeLock();
        this._marcarEstavel();
        this._atualizarEstadoMediaSession("playing");
      });

      v.addEventListener("pause", () => {
        this._liberarWakeLock();
        this._atualizarEstadoMediaSession("paused");
      });

      v.addEventListener("ended", () => {
        this._liberarWakeLock();
        this._atualizarEstadoMediaSession("none");
      });

      v.addEventListener("error", () => {
        // HLS/TS/DASH têm tratamento próprio; evita erro duplicado.
        const tipo = this._fonteAtual && this._fonteAtual.tipo;
        if (tipo && tipo !== "mp4") return;
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
      const {
        url,
        tipo = "hls",
        token = null,
        headers = null,
        fontes = null,
        fallbackUrl = null,
        fallbackTipo = null,
      } = opcoes;

      this._itemAtual = item;
      this._aoVivo = !!item.aoVivo;
      this._tentativas = 0;
      this._fonteIndice = 0;
      this._token = token || null;
      this._headers = headers || null;
      this._atualizarMediaSession(item);

      const lista = [];
      const vistos = new Set();
      const adicionar = (fonte) => {
        if (!fonte || !fonte.url || vistos.has(fonte.url)) return;
        vistos.add(fonte.url);
        lista.push({
          url: fonte.url,
          tipo: fonte.tipo || "hls",
          headers: fonte.headers || headers || null,
        });
      };

      if (Array.isArray(fontes) && fontes.length) {
        fontes.forEach(adicionar);
      } else if (url) {
        // .ts numérico costuma ter uma variante HLS contínua no mesmo caminho.
        if (tipo === "ts" && window.EFTV_SOURCE) {
          const variante = window.EFTV_SOURCE.varianteHls(url);
          if (variante) adicionar({ url: variante, tipo: "hls", headers });
        }
        adicionar({ url, tipo, headers });
      }
      if (fallbackUrl) {
        adicionar({ url: fallbackUrl, tipo: fallbackTipo || tipo, headers });
      }

      this._fontes = lista;
      if (!lista.length) {
        this._notify("error", new PlayerError("Este canal não possui URL de transmissão configurada.", "sem-url"));
        return;
      }

      try {
        await this._carregarFonte(0);
      } catch (erro) {
        this._notify("error", erro);
        throw erro;
      }
    },

    async _carregarFonte(indice) {
      const fonte = this._fontes[indice];
      if (!fonte) throw new PlayerError("Nenhuma fonte de transmissão disponível.", "sem-fonte");
      this._fonteIndice = indice;
      this._fonteAtual = fonte;
      this._geracao += 1;
      const geracao = this._geracao;
      this._limparMotores();

      this._notify("fonte", {
        indice: indice,
        total: this._fontes.length,
        proxy: window.EFTV_SOURCE ? window.EFTV_SOURCE.ehUrlProxy(fonte.url) : false,
      });

      try {
        switch (fonte.tipo) {
          case "hls": await this._loadHls(fonte, geracao); break;
          case "dash": await this._loadDash(fonte, geracao); break;
          case "ts": await this._loadTs(fonte, geracao); break;
          case "mp4": await this._loadMp4(fonte, geracao); break;
          default: throw new PlayerError("Tipo de stream não suportado: " + fonte.tipo, "tipo");
        }
      } catch (erro) {
        if (geracao !== this._geracao) return;

        // Retry no mesmo endereço com backoff exponencial.
        if (this._tentativas < this._maxTentativas) {
          this._tentativas += 1;
          const atraso = this._backoff(this._tentativas);
          this._notify("reconectando", { tentativa: this._tentativas, atraso });
          await new Promise((r) => setTimeout(r, atraso));
          if (geracao !== this._geracao) return;
          return this._carregarFonte(this._fonteIndice);
        }

        // Esgotou o mesmo endereço: tenta a próxima fonte (proxy/direto/HLS).
        const proxima = this._proximaFonte();
        if (proxima >= 0) {
          this._tentativas = 0;
          this._notify("reconectando", {
            tentativa: 0,
            atraso: 600,
            fonte: proxima + 1,
            totalFontes: this._fontes.length,
          });
          await new Promise((r) => setTimeout(r, 600));
          if (geracao !== this._geracao) return;
          return this._carregarFonte(proxima);
        }

        throw erro;
      }
    },

    _cabecalhos(fonte) {
      const h = { ...(fonte && fonte.headers ? fonte.headers : {}) };
      if (this._token) h.Authorization = "Bearer " + this._token;
      return h;
    },

    async _loadHls(fonte, geracao) {
      const video = this.video;
      const headers = this._cabecalhos(fonte);

      if (!window.Hls && video.canPlayType("application/vnd.apple.mpegurl")) {
        video.src = fonte.url;
        video.load();
        return new Promise((resolve, reject) => {
          const ok = () => {
            if (geracao !== this._geracao) return;
            this._notify("ready");
            resolve();
          };
          const erro = () => {
            if (geracao !== this._geracao) return;
            reject(new PlayerError("O navegador não conseguiu abrir o HLS.", "hls"));
          };
          video.addEventListener("loadedmetadata", ok, { once: true });
          video.addEventListener("error", erro, { once: true });
        });
      }

      if (!window.Hls) await carregarBiblioteca("hls.min.js");
      if (geracao !== this._geracao) return;

      this._destruirHls();
      const hls = new window.Hls({
        enableWorker: true,
        lowLatencyMode: this._aoVivo,
        liveDurationInfinity: this._aoVivo,
        backBufferLength: 30,
        maxBufferLength: 30,
        xhrSetup: (xhr) => {
          Object.entries(headers).forEach(([chave, valor]) => {
            try { xhr.setRequestHeader(chave, valor); } catch (_) {}
          });
        },
      });
      this.hls = hls;

      return new Promise((resolve, reject) => {
        let resolvido = false;

        hls.on(window.Hls.Events.MANIFEST_PARSED, () => {
          if (geracao !== this._geracao) return;
          resolvido = true;
          this._notify("ready");
          resolve();
        });

        hls.on(window.Hls.Events.LEVEL_LOADED, (_e, data) => {
          if (geracao !== this._geracao) return;
          if (data && data.details && data.details.live) this._notify("live");
        });

        hls.on(window.Hls.Events.ERROR, (_e, data) => {
          if (geracao !== this._geracao || !data.fatal) return;

          // Recuperação leve antes de trocar de fonte.
          if (data.type === window.Hls.ErrorTypes.MEDIA_ERROR && this._tentativas < 2) {
            this._tentativas += 1;
            const atraso = this._backoff(this._tentativas);
            this._notify("reconectando", { tentativa: this._tentativas, atraso });
            setTimeout(() => {
              if (geracao !== this._geracao || !this.hls) return;
              try { this.hls.recoverMediaError(); } catch (_) {}
            }, atraso);
            return;
          }

          if (this._tentativas < this._maxTentativas) {
            this._tentativas += 1;
            const atraso = this._backoff(this._tentativas);
            this._notify("reconectando", { tentativa: this._tentativas, atraso });
            setTimeout(() => {
              if (geracao !== this._geracao || !this.hls) return;
              try { this.hls.startLoad(); } catch (_) {}
            }, atraso);
            return;
          }

          const err = new PlayerError(
            "Não foi possível carregar a transmissão (" + data.details + ").",
            "hls"
          );
          const proxima = this._proximaFonte();
          if (resolvido && proxima >= 0) {
            this._tentativas = 0;
            this._notify("reconectando", {
              tentativa: 0,
              atraso: 600,
              fonte: proxima + 1,
              totalFontes: this._fontes.length,
            });
            setTimeout(() => {
              this._carregarFonte(proxima).catch(() => {});
            }, 600);
            return;
          }
          this._notify("error", err);
          if (!resolvido) reject(err);
        });
      });
    },

    async _loadDash(fonte, geracao) {
      if (!window.dashjs) await carregarBiblioteca("dash.all.min.js");
      if (geracao !== this._geracao) return;
      this._destruirDash();
      const headers = this._cabecalhos(fonte);
      const dash = window.dashjs.MediaPlayer().create();
      this.dashPlayer = dash;
      dash.initialize(this.video, fonte.url, false);
      if (Object.keys(headers).length) {
        try { dash.setXHRWithCredentialsForType("GET", false); } catch (_) {}
        try {
          dash.setProtectionData({
            "com.widevine.alpha": { serverURL: "", httpRequestHeaders: headers },
          });
        } catch (_) {}
      }

      return new Promise((resolve, reject) => {
        let resolvido = false;
        dash.on(window.dashjs.MediaPlayer.events.STREAM_INITIALIZED, () => {
          if (geracao !== this._geracao) return;
          resolvido = true;
          this._notify("ready");
          resolve();
        });
        dash.on(window.dashjs.MediaPlayer.events.ERROR, (e) => {
          if (geracao !== this._geracao) return;
          const err = new PlayerError("Erro DASH: " + ((e.error && e.error.message) || e), "dash");
          if (resolvido) {
            const proxima = this._proximaFonte();
            if (proxima >= 0) {
              this._tentativas = 0;
              setTimeout(() => this._carregarFonte(proxima).catch(() => {}), 600);
              return;
            }
            this._notify("error", err);
            return;
          }
          reject(err);
        });
      });
    },

    async _loadTs(fonte, geracao) {
      if (!window.mpegts || typeof window.mpegts.createPlayer !== "function") {
        await carregarBiblioteca("mpegts.js");
      }
      if (geracao !== this._geracao) return;
      this._destruirTs();
      const headers = this._cabecalhos(fonte);
      this.tsPlayer = window.mpegts.createPlayer(
        { type: "mse", isLive: this._aoVivo, url: fonte.url, cors: true },
        {
          enableWorker: true,
          liveBufferLatencyChasing: this._aoVivo,
          headers: Object.keys(headers).length ? headers : undefined,
        }
      );
      this.tsPlayer.attachMediaElement(this.video);
      this.tsPlayer.load();

      return new Promise((resolve, reject) => {
        let resolvido = false;
        const pronto = () => {
          if (geracao !== this._geracao || resolvido) return;
          resolvido = true;
          this._notify("ready");
          resolve();
        };
        this.tsPlayer.on(window.mpegts.Events.MEDIA_INFO, () => {
          if (geracao !== this._geracao) return;
          if (this._aoVivo) this._notify("live");
          pronto();
        });
        // mpegts.js não expõe LOADED_METADATA; o vídeo avisa quando o MSE
        // já tem metadados suficientes para tocar.
        this.video.addEventListener("loadedmetadata", pronto, { once: true });
        this.tsPlayer.on(window.mpegts.Events.ERROR, (_t, detalhe) => {
          if (geracao !== this._geracao) return;
          const err = new PlayerError("Erro MPEG-TS: " + detalhe, "ts");
          if (resolvido) {
            const proxima = this._proximaFonte();
            if (proxima >= 0) {
              this._tentativas = 0;
              setTimeout(() => this._carregarFonte(proxima).catch(() => {}), 600);
              return;
            }
            this._notify("error", err);
            return;
          }
          reject(err);
        });
      });
    },

    _loadMp4(fonte, geracao) {
      const video = this.video;
      return new Promise((resolve, reject) => {
        const ok = () => {
          limpar();
          if (geracao !== this._geracao) return;
          this._notify("ready");
          resolve();
        };
        const erro = () => {
          limpar();
          if (geracao !== this._geracao) return;
          reject(new PlayerError("O navegador não conseguiu abrir este vídeo (codec/container).", "mp4"));
        };
        const limpar = () => {
          video.removeEventListener("loadedmetadata", ok);
          video.removeEventListener("error", erro);
        };
        video.addEventListener("loadedmetadata", ok);
        video.addEventListener("error", erro);
        video.src = fonte.url;
        video.load();
      });
    },

    _backoff(tentativa) {
      const base = Math.min(15000, 1000 * Math.pow(2, Math.max(0, tentativa - 1)));
      return base + Math.floor(Math.random() * 400);
    },

    _marcarEstavel() {
      if (this._estavelTimer) clearTimeout(this._estavelTimer);
      this._estavelTimer = setTimeout(() => {
        this._tentativas = 0;
      }, 30000);
    },

    /** Índice da próxima fonte, ou -1 quando já tentou todas. */
    _proximaFonte() {
      if (this._fonteIndice + 1 >= this._fontes.length) return -1;
      return this._fonteIndice + 1;
    },

    _limparMotores() {
      this._destruirHls();
      this._destruirDash();
      this._destruirTs();
      if (this.video) {
        try {
          this.video.pause();
          this.video.removeAttribute("src");
          this.video.load();
        } catch (_) {}
      }
    },

    // ---------- Controles ----------
    play() {
      if (!this.video) return Promise.reject(new PlayerError("Vídeo não iniciado"));
      return this.video.play();
    },
    pause() { if (this.video) this.video.pause(); },
    toggle() { return this.video && this.video.paused ? this.play() : this.pause(); },

    stop() {
      this._geracao += 1;
      this._pararHeartbeat();
      this._pararProgresso();
      this._limparMediaSession();
      this._liberarWakeLock();
      if (this._estavelTimer) clearTimeout(this._estavelTimer);
      this._estavelTimer = null;
      this._limparMotores();
      this._fontes = [];
      this._fonteAtual = null;
      this._fonteIndice = 0;
      this._itemAtual = null;
      this._aoVivo = false;
      this._token = null;
      this._headers = null;
    },

    /** Recarrega a fonte atual (botão "Tentar novamente" / troca de proxy). */
    recarregar() {
      if (!this._fontes.length) return Promise.reject(new PlayerError("Nada para recarregar."));
      this._tentativas = 0;
      return this._carregarFonte(this._fonteIndice);
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
      if (this._fonteAtual && this._fonteAtual.tipo === "ts") {
        this._carregarFonte(this._fonteIndice).catch(() => {});
        return;
      }
      if (this.dashPlayer) {
        try {
          const dur = this.dashPlayer.duration();
          if (Number.isFinite(dur) && dur > 0) this.dashPlayer.seek(dur);
        } catch (_) {}
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
        resultado.qualidade.push({
          id: -1,
          rotulo: "Auto",
          ativo: this.hls.autoLevelEnabled,
        });
        (this.hls.levels || []).forEach((nivel, i) => {
          resultado.qualidade.push({
            id: i,
            rotulo: nivel.height ? nivel.height + "p" : (nivel.name || "Nível " + (i + 1)),
            ativo: !this.hls.autoLevelEnabled && this.hls.currentLevel === i,
          });
        });
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
          const atual = this.dashPlayer.getQualityFor("video");
          resultado.qualidade = lista.map((q, i) => ({
            id: i,
            rotulo: (q.height ? q.height + "p" : Math.round(q.bitrate / 1000) + " kbps"),
            ativo: atual === i,
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
      const numero = Number(id);
      if (this.hls) this.hls.currentLevel = numero < 0 ? -1 : numero;
      if (this.dashPlayer) {
        try {
          if (numero < 0) this.dashPlayer.updateSettings({ streaming: { abr: { autoSwitchBitrate: { video: true } } } });
          else {
            this.dashPlayer.updateSettings({ streaming: { abr: { autoSwitchBitrate: { video: false } } } });
            this.dashPlayer.setQualityFor("video", numero, true);
          }
        } catch (_) {}
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

    // ---------- Overscan ----------
    // Margem de segurança para TVs que cortam as bordas. Aplica só na
    // interface; o player em tela cheia continua ocupando a tela toda,
    // como no Android.
    setOverscan(percentual) {
      const pct = Math.max(0, Math.min(10, Number(percentual) || 0));
      const px = Math.round(pct * 8);
      document.documentElement.style.setProperty("--overscan-px", px + "px");
      document.documentElement.style.setProperty("--overscan-scale", String(1 - pct / 100));
      return pct;
    },

    // ---------- Wake Lock ----------
    async _solicitarWakeLock() {
      if (!("wakeLock" in navigator) || this._wakeLock) return;
      try {
        this._wakeLock = await navigator.wakeLock.request("screen");
        this._wakeLock.addEventListener("release", () => { this._wakeLock = null; });
        this._notify("wakelock", { ativo: true });
      } catch (_) {
        this._wakeLock = null;
      }
    },

    _liberarWakeLock() {
      if (!this._wakeLock) return;
      try { this._wakeLock.release(); } catch (_) {}
      this._wakeLock = null;
      this._notify("wakelock", { ativo: false });
    },

    temWakeLock() {
      return !!this._wakeLock;
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

    _atualizarEstadoMediaSession(estado) {
      if (!("mediaSession" in navigator)) return;
      try { navigator.mediaSession.playbackState = estado; } catch (_) {}
    },

    _limparMediaSession() {
      if (!("mediaSession" in navigator)) return;
      try {
        navigator.mediaSession.metadata = null;
        navigator.mediaSession.playbackState = "none";
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
