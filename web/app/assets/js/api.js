/* ============================================================
   EFTV — Cliente da API
   Espelha os endpoints usados pelo app Android (backend FastAPI).
   ============================================================ */

(() => {
  "use strict";

  const cfg = window.EFTV_CONFIG;
  const store = window.EFTV_STORE;

  class ApiError extends Error {
    constructor(mensagem, status, corpo) {
      super(mensagem);
      this.name = "ApiError";
      this.status = status;
      this.corpo = corpo;
    }
  }

  let refreshEmAndamento = null;

  function urlBase() {
    return (cfg.API_URL || "").replace(/\/+$/, "");
  }

  function headersPadrao(comAuth) {
    const h = {
      "Content-Type": "application/json",
      "X-Device-Id": store.deviceId(),
    };
    if (comAuth) {
      const sessao = store.getSession();
      if (sessao && sessao.access) h.Authorization = "Bearer " + sessao.access;
    }
    return h;
  }

  async function request(caminho, opcoes = {}) {
    const {
      method = "GET",
      body = null,
      auth = false,
      retry = true,
      timeout = 15000,
      raw = false,
    } = opcoes;

    const controlador = new AbortController();
    const relogio = setTimeout(() => controlador.abort(), timeout);

    let resposta;
    try {
      resposta = await fetch(urlBase() + caminho, {
        method,
        headers: headersPadrao(auth),
        body: body ? JSON.stringify(body) : null,
        signal: controlador.signal,
        credentials: "include",
      });
    } catch (erro) {
      clearTimeout(relogio);
      throw new ApiError(
        erro.name === "AbortError" ? "Tempo esgotado ao conectar." : "Falha de conexão com o servidor.",
        0,
        null
      );
    }
    clearTimeout(relogio);

    // 401: tenta renovar o access token uma vez
    if (resposta.status === 401 && auth && retry) {
      const renovou = await tentarRefresh();
      if (renovou) return request(caminho, { ...opcoes, retry: false });
    }

    if (raw) return resposta;

    let corpo = null;
    const texto = await resposta.text();
    if (texto) {
      try { corpo = JSON.parse(texto); } catch (_) { corpo = texto; }
    }

    if (!resposta.ok) {
      const detalhe = corpo && (corpo.detail || corpo.error || corpo.message);
      const msg =
        (typeof detalhe === "string" && detalhe) ||
        (detalhe && (detalhe.message || detalhe.code)) ||
        "Erro HTTP " + resposta.status;
      throw new ApiError(String(msg), resposta.status, corpo);
    }
    return corpo;
  }

  async function tentarRefresh() {
    const sessao = store.getSession();
    if (!sessao || !sessao.refresh) return false;
    if (refreshEmAndamento) return refreshEmAndamento;

    refreshEmAndamento = (async () => {
      try {
        const dados = await request("/auth/refresh", {
          method: "POST",
          body: { refresh_token: sessao.refresh },
          retry: false,
        });
        if (dados && dados.access_token) {
          store.setSession({
            ...sessao,
            access: dados.access_token,
            refresh: dados.refresh_token || sessao.refresh,
          });
          return true;
        }
        return false;
      } catch (_) {
        store.clearSession();
        return false;
      } finally {
        refreshEmAndamento = null;
      }
    })();

    return refreshEmAndamento;
  }

  const api = {
    ApiError,
    request,
    urlBase,

    // ---------- Auth ----------
    async login(email, senha) {
      const dados = await request("/auth/login", {
        method: "POST",
        body: { email, password: senha },
      });
      const sessao = {
        access: dados.access_token,
        refresh: dados.refresh_token,
        email,
      };
      store.setSession(sessao);
      return dados;
    },

    async registrar(nome, email, senha) {
      return request("/auth/register", {
        method: "POST",
        body: { full_name: nome, email, password: senha },
      });
    },

    async me() {
      return request("/auth/me", { auth: true });
    },

    async logout() {
      const sessao = store.getSession();
      store.clearSession();
      if (sessao && sessao.refresh) {
        try {
          await request("/auth/logout", {
            method: "POST",
            body: { refresh_token: sessao.refresh },
            retry: false,
          });
        } catch (_) {}
      }
    },

    async esqueciSenha(email) {
      return request("/auth/forgot-password", { method: "POST", body: { email } });
    },

    async redefinirSenha(email, codigo, novaSenha) {
      return request("/auth/reset-password", {
        method: "POST",
        body: { email, code: codigo, new_password: novaSenha },
      });
    },

    async verificarEmail(token) {
      return request("/auth/verify-email", { method: "POST", body: { token } });
    },

    // ---------- Catálogo ----------
    async categorias(incluirAdulto = false) {
      return request("/categories?include_adult=" + (incluirAdulto ? "true" : "false"));
    },

    async canais(params = {}) {
      const q = new URLSearchParams();
      Object.entries(params).forEach(([k, v]) => {
        if (v !== undefined && v !== null && v !== "") q.set(k, v);
      });
      const sufixo = q.toString() ? "?" + q.toString() : "";
      return request("/channels" + sufixo);
    },

    // O backend pagina (máx. 100 por página): busca todas as páginas.
    async canaisTodas(params = {}) {
      const tamanho = Math.min(Number(params.page_size) || 100, 100);
      const primeiro = await api.canais({ ...params, page: 1, page_size: tamanho });
      const lista = (primeiro && primeiro.channels) || [];
      const totalPaginas = (primeiro && primeiro.total_pages) || 1;
      for (let pagina = 2; pagina <= totalPaginas; pagina++) {
        const proximo = await api.canais({ ...params, page: pagina, page_size: tamanho });
        if (proximo && Array.isArray(proximo.channels)) lista.push(...proximo.channels);
      }
      return { channels: lista, total: lista.length };
    },

    async canal(slug) {
      return request("/channels/" + encodeURIComponent(slug), { auth: true });
    },

    // ---------- Player ----------
    // Texto M3U buscado pelo backend (fallback de DNS/CORS no navegador).
    // Pode demorar: o backend baixa a playlist do provedor.
    async playlistTexto() {
      return request("/player/playlist-text", { auth: true, timeout: 130000 });
    },

    async iniciarPlayer(channelUrl, channelName) {
      return request("/player/play", {
        method: "POST",
        auth: true,
        body: { channel_url: channelUrl, channel_name: channelName || null },
      });
    },

    async heartbeatPlayer(sessionId) {
      return request("/player/heartbeat", {
        method: "POST",
        auth: true,
        body: { session_id: sessionId },
      });
    },

    async pararPlayer(sessionId) {
      return request("/player/stop", {
        method: "POST",
        auth: true,
        body: { session_id: sessionId },
      });
    },

    async dispositivo() {
      return request("/player/device", { auth: true });
    },

    async revogarDispositivos() {
      return request("/player/device/revoke-all", { method: "POST", auth: true });
    },

    // ---------- Assinatura ----------
    async assinatura() {
      return request("/subscriptions/current", { auth: true });
    },

    async planos() {
      return request("/plans");
    },

    async checkout(planoId) {
      const base = new URL("checkout.html", location.href).href;
      return request("/subscriptions/checkout", {
        method: "POST",
        auth: true,
        body: {
          plan_id: planoId,
          back_urls: {
            success: base + "?status=success",
            failure: base + "?status=failure",
            pending: base + "?status=pending",
          },
        },
      });
    },

    async cancelar(subscriptionId) {
      return request("/subscriptions/" + encodeURIComponent(subscriptionId) + "/cancel", {
        method: "POST",
        auth: true,
      });
    },

    // Reconsulta o resumo da assinatura (usado em "Restaurar compras").
    async sincronizarAssinatura() {
      return request("/subscriptions/current", { auth: true });
    },

    // ---------- App ----------
    async reportarErro(dados) {
      try {
        await request("/app/crashes", {
          method: "POST",
          body: {
            message: String(dados.message || "").slice(0, 500),
            stacktrace: String(dados.stack || "").slice(0, 8000),
            app_version: String(dados.version || "").slice(0, 32),
            device: String(dados.device || "").slice(0, 120),
            android: "web",
          },
          timeout: 3000,
        });
      } catch (_) {}
    },

    // ---------- Login por código (TV) ----------
    async gerarCodigoTV() {
      return request("/auth/device-code", { method: "POST" });
    },

    async consultarCodigoTV(codigo) {
      return request("/auth/device-code/poll?code=" + encodeURIComponent(codigo));
    },
  };

  window.EFTV_API = api;
})();