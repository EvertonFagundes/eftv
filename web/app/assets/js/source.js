/* ============================================================
   EFTV — Fonte de mídia e servidor local
   Decide entre URL direta e proxy (server.py) e resolve o catálogo
   magro do modo local (/api/catalogo.json + /api/canal?slug=).
   Nenhuma credencial de playlist é logada ou exibida.
   ============================================================ */

(() => {
  "use strict";

  const cfg = window.EFTV_CONFIG;
  const store = window.EFTV_STORE;
  const CHAVE_PROXY = "proxy_url";

  const status = {
    testado: false,
    disponivel: false,
    mesmoServidor: false,
    base: "",
    motivo: "não testado",
    versao: "",
    canais: 0,
    playlists: 0,
  };

  let deteccao = null;

  function normalizarBase(valor) {
    let base = String(valor || "").trim();
    if (!base) return "";
    base = base.replace(/\/+$/, "");
    if (!/^https?:\/\//i.test(base)) return "";
    return base;
  }

  function baseConfigurada() {
    return normalizarBase(store.ler(CHAVE_PROXY, "") || cfg.PROXY_URL || "");
  }

  function paginaHttps() {
    return location.protocol === "https:";
  }

  function proxyPermitido(base) {
    if (!base) return false;
    // Página HTTPS não pode falar com http://127.0.0.1 (mixed content).
    if (paginaHttps() && /^http:\/\//i.test(base)) return false;
    return true;
  }

  function absoluta(url) {
    const valor = String(url || "").trim();
    if (!valor) return "";
    if (/^(https?:|data:|blob:)/i.test(valor)) return valor;
    if (valor.startsWith("//")) return location.protocol + valor;
    if (valor.startsWith("/")) {
      if (status.base && valor.startsWith("/api/")) return status.base + valor;
      return location.origin + valor;
    }
    try {
      return new URL(valor, location.href).href;
    } catch (_) {
      return valor;
    }
  }

  function apiPath(caminho) {
    return status.base ? status.base + caminho : caminho;
  }

  function ehUrlProxy(url) {
    return /\/api\/proxy\?/i.test(String(url || ""));
  }

  function proxyUrl(url) {
    if (!url) return "";
    if (ehUrlProxy(url)) return absoluta(url);
    if (!status.disponivel) return "";
    const destino = /^https?:\/\//i.test(url) ? url : absoluta(url);
    return apiPath("/api/proxy?url=" + encodeURIComponent(destino));
  }

  function remotePlaylistUrl(url, doh) {
    if (!url) return "";
    if (!status.disponivel) return "";
    return apiPath(
      "/api/playlist-remote?url=" + encodeURIComponent(url) + (doh ? "&doh=1" : "")
    );
  }

  /**
   * Detecta o server.py na mesma origem (self-hosted) ou em uma URL
   * configurada. O GitHub Pages não tem /api/status; nesse caso o app segue
   * direto, sujeito ao CORS do provedor.
   */
  function detectar(forcar = false) {
    if (deteccao && !forcar) return deteccao;

    deteccao = (async () => {
      status.testado = true;
      status.disponivel = false;
      status.mesmoServidor = false;
      status.base = "";
      status.motivo = "sem servidor local";
      status.versao = "";
      status.canais = 0;
      status.playlists = 0;

      async function consultar(base, mesmoServidor) {
        const alvo = (base || "") + "/api/status";
        const controlador = new AbortController();
        const relogio = setTimeout(() => controlador.abort(), 3500);
        try {
          const resposta = await fetch(alvo, {
            cache: "no-store",
            credentials: "omit",
            signal: controlador.signal,
          });
          if (!resposta.ok) return false;
          const dados = await resposta.json();
          if (!dados || !dados.ok) return false;
          status.disponivel = true;
          status.mesmoServidor = !!mesmoServidor;
          status.base = base || "";
          status.versao = dados.versao || "";
          status.canais = Number(dados.canais) || 0;
          status.playlists = Number(dados.playlists) || 0;
          status.motivo = mesmoServidor ? "servidor local na mesma origem" : "proxy local configurado";
          return true;
        } catch (_) {
          return false;
        } finally {
          clearTimeout(relogio);
        }
      }

      // 1) O próprio server.py servindo o PWA (http://127.0.0.1:8124/web/app/).
      if (location.protocol === "http:" || location.protocol === "https:") {
        if (await consultar("", true)) return { ...status };
      }

      // 2) Proxy explícito (config.js ou Ajustes). Em página HTTPS, só https.
      const base = baseConfigurada();
      if (base && proxyPermitido(base)) {
        if (await consultar(base, false)) return { ...status };
        status.motivo = "proxy configurado, mas não respondeu";
      } else if (base && paginaHttps()) {
        status.motivo = "proxy http bloqueado por mixed content";
      }

      return { ...status };
    })();

    return deteccao;
  }

  function definirProxy(url) {
    const base = normalizarBase(url);
    if (base) store.gravar(CHAVE_PROXY, base);
    else store.remover(CHAVE_PROXY);
    deteccao = null;
    status.testado = false;
    return detectar(true);
  }

  function varianteHls(url) {
    const texto = String(url || "");
    const partes = texto.split("?");
    const caminho = partes[0];
    const nome = caminho.slice(caminho.lastIndexOf("/") + 1);
    if (!nome.toLowerCase().endsWith(".ts")) return "";
    const base = nome.slice(0, -3);
    if (!/^\d+$/.test(base)) return "";
    return caminho.slice(0, -3) + ".m3u8" + (partes.length > 1 ? "?" + partes.slice(1).join("?") : "");
  }

  function temHeaders(headers) {
    return !!headers && Object.keys(headers).length > 0;
  }

  /**
   * Lista de URLs a tentar, em ordem. O player troca de candidato quando a
   * fonte falha (equivalente ao tryPlaybackFallback do Android).
   */
  function candidatos(url, opcoes = {}) {
    const original = String(url || "").trim();
    if (!original) return [];
    if (ehUrlProxy(original)) {
      return [{ url: absoluta(original), proxy: true, headers: null }];
    }

    const headers = opcoes.headers || null;
    const misto = paginaHttps() && /^http:\/\//i.test(original);
    const local =
      !/^https?:\/\//i.test(original) || original.startsWith(location.origin + "/");
    const usarProxy = status.disponivel && !local &&
      (opcoes.forcarProxy || misto || temHeaders(headers) ||
        store.getSettings().proxyStreams !== false);

    const lista = [];
    const vistos = new Set();
    function adicionar(item) {
      if (!item.url || vistos.has(item.url)) return;
      vistos.add(item.url);
      lista.push(item);
    }

    if (usarProxy) {
      adicionar({ url: proxyUrl(original), proxy: true, headers: null });
    }

    if (!misto) {
      adicionar({ url: original, proxy: false, headers });
    } else if (!status.disponivel) {
      const https = original.replace(/^http:/i, "https:");
      if (https !== original) adicionar({ url: https, proxy: false, headers });
    }

    if (status.disponivel && !usarProxy) {
      adicionar({ url: proxyUrl(original), proxy: true, headers: null });
    }

    return lista;
  }

  function candidatosFonte(fonte) {
    if (!fonte || !fonte.url) return [];
    const url = absoluta(fonte.url);
    const lista = [{ url, proxy: ehUrlProxy(url), headers: fonte.headers || null }];
    if (fonte.fallbackUrl) {
      lista.push({
        url: absoluta(fonte.fallbackUrl),
        proxy: ehUrlProxy(fonte.fallbackUrl),
        headers: fonte.headers || null,
        tipo: fonte.fallbackTipo || null,
      });
    }
    return lista;
  }

  async function catalogoLocal() {
    if (!status.disponivel) return null;
    const resposta = await fetch(apiPath("/api/catalogo.json"), { cache: "no-store" });
    if (!resposta.ok) throw new Error("O servidor local não devolveu o catálogo (HTTP " + resposta.status + ").");
    const dados = await resposta.json();
    return dados && Array.isArray(dados.canais) ? dados : null;
  }

  async function canalLocal(slug) {
    if (!status.disponivel) return null;
    const resposta = await fetch(
      apiPath("/api/canal?slug=" + encodeURIComponent(slug)),
      { cache: "no-store" }
    );
    if (!resposta.ok) throw new Error("Transmissão não encontrada no servidor local (HTTP " + resposta.status + ").");
    const dados = await resposta.json();
    return dados && dados.canal ? dados.canal : null;
  }

  function absolutizarCanal(canal) {
    if (!canal) return canal;
    const copia = { ...canal };
    if (copia.logo) copia.logo = absoluta(copia.logo);
    if (Array.isArray(copia.fontes)) {
      copia.fontes = copia.fontes.map((f) => ({
        ...f,
        url: absoluta(f.url),
        fallbackUrl: f.fallbackUrl ? absoluta(f.fallbackUrl) : f.fallbackUrl,
      }));
    }
    return copia;
  }

  function statusTexto() {
    if (!status.testado) return "Verificando servidor local…";
    if (!status.disponivel) return "Sem proxy local: o navegador tenta a URL direta do provedor.";
    const onde = status.mesmoServidor ? "nesta origem" : status.base;
    const canais = status.canais ? ` · ${status.canais} canais` : "";
    return `Proxy local ativo em ${onde}${canais}. Streams passam pelo servidor.`;
  }

  window.EFTV_SOURCE = {
    detectar,
    definirProxy,
    baseConfigurada,
    proxyUrl,
    remotePlaylistUrl,
    candidatos,
    candidatosFonte,
    catalogoLocal,
    canalLocal,
    absolutizarCanal,
    absoluta,
    varianteHls,
    ehUrlProxy,
    status: () => ({ ...status }),
    statusTexto,
  };
})();
