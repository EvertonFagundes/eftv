/* EFTV - armazenamento local para o modo estático (GitHub Pages).
   No GitHub Pages não existe server.py: as playlists ficam no IndexedDB do
   navegador, são lidas no cliente e os streams tocam direto (sujeitos a CORS).
   No servidor local este arquivo não faz nada. */

(function () {
  if (!window.CANAIS_STATIC || !window.CANAIS_DATA) return;

  const DB_NAME = "eftv-local";
  const STORE = "playlists";
  const DB_VERSION = 1;
  const MAX_CHANNELS = 50000;

  // Aviso de modo estático.
  document.querySelectorAll("[data-static-banner]").forEach((el) => {
    el.hidden = false;
  });

  function abrirDB() {
    return new Promise((resolve, reject) => {
      const req = indexedDB.open(DB_NAME, DB_VERSION);
      req.onupgradeneeded = () => {
        const db = req.result;
        if (!db.objectStoreNames.contains(STORE)) {
          db.createObjectStore(STORE, { keyPath: "id" });
        }
      };
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error || new Error("IndexedDB indisponível."));
    });
  }

  async function listar() {
    const db = await abrirDB();
    return new Promise((resolve, reject) => {
      const tx = db.transaction(STORE, "readonly");
      const req = tx.objectStore(STORE).getAll();
      req.onsuccess = () => resolve(req.result || []);
      req.onerror = () => reject(req.error);
    });
  }

  async function salvar(playlist) {
    const db = await abrirDB();
    return new Promise((resolve, reject) => {
      const tx = db.transaction(STORE, "readwrite");
      tx.objectStore(STORE).put(playlist);
      tx.oncomplete = () => resolve(playlist);
      tx.onerror = () => reject(tx.error);
    });
  }

  async function removerDoBanco(id) {
    const db = await abrirDB();
    return new Promise((resolve, reject) => {
      const tx = db.transaction(STORE, "readwrite");
      tx.objectStore(STORE).delete(id);
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    });
  }

  async function limparBanco() {
    const db = await abrirDB();
    return new Promise((resolve, reject) => {
      const tx = db.transaction(STORE, "readwrite");
      tx.objectStore(STORE).clear();
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    });
  }

  function novoId() {
    if (window.crypto && typeof window.crypto.randomUUID === "function") {
      return window.crypto.randomUUID().replace(/-/g, "").slice(0, 10);
    }
    return Math.random().toString(16).slice(2, 12).padEnd(10, "0");
  }

  function agoraISO() {
    return new Date().toISOString();
  }

  function nomeDaUrl(url) {
    try {
      const u = new URL(url);
      const base = decodeURIComponent(u.pathname.split("/").pop() || "");
      return base.replace(/\.(m3u8?|mpd|mp4|ts)$/i, "").replace(/[_-]+/g, " ").trim() || u.hostname;
    } catch (_) {
      return "Playlist";
    }
  }

  function resolverUrl(valor, base) {
    const v = String(valor || "").trim();
    if (!v) return "";
    if (/^(data:|blob:|https?:)/i.test(v)) return v;
    if (!base) return v;
    try {
      return new URL(v, base).href;
    } catch (_) {
      return v;
    }
  }

  function atributos(linha) {
    const attrs = {};
    const re = /([A-Za-z0-9_-]+)="([^"]*)"/g;
    let m;
    while ((m = re.exec(linha))) attrs[m[1].toLowerCase()] = m[2];
    return attrs;
  }

  function pareceManifestoHls(texto) {
    return /#EXT-X-(STREAM-INF|TARGETDURATION|MEDIA-SEQUENCE)/i.test(texto) && !/#EXTINF/i.test(texto);
  }

  function parsePlaylist(texto, nome, url) {
    const linhas = String(texto || "").split(/\r?\n/);
    const canais = [];
    let pendente = null;
    let truncada = false;

    if (pareceManifestoHls(texto)) {
      if (url) {
        canais.push({ name: nome || nomeDaUrl(url), group: "", logo: "", url });
      }
      return { channels: canais, truncated: false };
    }

    for (const bruta of linhas) {
      const linha = bruta.trim();
      if (!linha) continue;

      if (linha.startsWith("#EXTINF")) {
        const attrs = atributos(linha);
        const virgula = linha.lastIndexOf(",");
        const nomeCanal = (virgula >= 0 ? linha.slice(virgula + 1) : "").trim();
        pendente = {
          name: nomeCanal || attrs["tvg-name"] || "",
          group: attrs["group-title"] || "",
          logo: resolverUrl(attrs["tvg-logo"] || "", url),
        };
        continue;
      }

      if (linha.startsWith("#")) continue;
      if (!/^(https?:|data:|blob:)/i.test(linha)) continue;

      const endereco = resolverUrl(linha, url);
      if (!endereco) continue;
      canais.push({
        name: (pendente && pendente.name) || endereco.split("/").pop() || `Canal ${canais.length + 1}`,
        group: (pendente && pendente.group) || "",
        logo: (pendente && pendente.logo) || "",
        url: endereco,
      });
      pendente = null;

      if (canais.length >= MAX_CHANNELS) {
        truncada = true;
        break;
      }
    }

    return { channels: canais, truncated: truncada };
  }

  function inferirTipo(url) {
    let caminho = String(url || "").split("#")[0].split("?")[0].toLowerCase();
    if (caminho.endsWith(".mpd")) return "dash";
    if (caminho.endsWith(".ts")) return "ts";
    if (/\.(mp4|m4v|webm|mkv|avi|mov|mpeg|mpg)$/.test(caminho)) return "mp4";
    return "hls";
  }

  function varianteHls(url) {
    try {
      const u = new URL(url);
      if (!u.pathname.toLowerCase().endsWith(".ts")) return "";
      const nome = u.pathname.split("/").pop() || "";
      if (!/^\d+\.ts$/i.test(nome)) return "";
      u.pathname = u.pathname.slice(0, -3) + ".m3u8";
      return u.href;
    } catch (_) {
      return "";
    }
  }

  function criarCanal(playlist, canal, indice) {
    const tipo = inferirTipo(canal.url);
    const aoVivo = tipo === "hls" || tipo === "ts" || tipo === "dash";
    const hls = varianteHls(canal.url);
    const fontes = hls
      ? [
          {
            label: "HLS",
            nome: canal.name,
            tipo: "hls",
            demo: false,
            url: hls,
            fallbackTipo: "ts",
            fallbackUrl: canal.url,
          },
        ]
      : [
          {
            label: "Opção 1",
            nome: canal.name,
            tipo,
            demo: false,
            url: canal.url,
          },
        ];

    return {
      slug: `ext-${playlist.id}-${indice}`,
      nome: canal.name,
      categoria: window.canaisCategoria(canal.group),
      grupo: canal.group,
      logo: canal.logo,
      aoVivo,
      agora: {
        titulo: canal.group || (aoVivo ? "Transmissão ao vivo" : "Conteúdo sob demanda"),
        inicio: "--:--",
        fim: "--:--",
        descricao: aoVivo
          ? `Canal importado da playlist ${playlist.name}.`
          : `Vídeo sob demanda da playlist ${playlist.name}.`,
      },
      aSeguir: "Programação não disponível",
      origem: { playlist: playlist.name, playlistId: playlist.id },
      fontes,
    };
  }

  function resumir(playlist) {
    return {
      id: playlist.id,
      name: playlist.name,
      url: playlist.url || "",
      count: (playlist.channels || []).length,
      importedAt: playlist.imported_at || "",
      updatedAt: playlist.updated_at || "",
      uploaded: !playlist.url,
    };
  }

  async function reconstruir() {
    const playlists = await listar();
    const canais = [];
    playlists.forEach((playlist) => {
      (playlist.channels || []).forEach((canal, indice) => {
        if (canal.url) canais.push(criarCanal(playlist, canal, indice));
      });
    });

    const resumos = playlists.map(resumir);
    if (typeof window.CanaisAplicarCatalogo === "function") {
      window.CanaisAplicarCatalogo({
        playlists: resumos,
        categorias: canais.length ? (window.CANAIS_CATEGORIAS || []).map(({ id, nome }) => ({ id, nome })) : [],
        canais,
      });
    } else {
      window.CANAIS_DATA.canais = canais;
      window.CANAIS_EXTRA_PLAYLISTS = resumos;
    }

    window.CANAIS_CATALOGO_PRONTO = true;
    window.CANAIS_STATIC_READY = true;
    document.dispatchEvent(new CustomEvent("eftv:catalogo-pronto"));
    return resumos;
  }

  async function adicionarTexto(texto, nome, url) {
    const { channels, truncated } = parsePlaylist(texto, nome, url);
    if (!channels.length) {
      throw new Error("A playlist não contém canais reproduzíveis.");
    }
    const playlist = {
      id: novoId(),
      name: nome || (url ? nomeDaUrl(url) : "Playlist"),
      url: url || "",
      channels,
      truncated,
      imported_at: agoraISO(),
      updated_at: agoraISO(),
    };
    await salvar(playlist);
    await reconstruir();
    return {
      message: `${channels.length.toLocaleString("pt-BR")} ${
        channels.length === 1 ? "canal importado" : "canais importados"
      } de ${playlist.name}.${truncated ? ` A lista foi limitada aos primeiros ${MAX_CHANNELS.toLocaleString("pt-BR")} canais.` : ""}`,
      playlist: resumir(playlist),
    };
  }

  async function adicionarUrl(url) {
    let resposta;
    try {
      resposta = await fetch(url, { cache: "no-store", mode: "cors" });
    } catch (_) {
      throw new Error(
        "O navegador não conseguiu baixar a playlist por CORS. No GitHub Pages não há proxy: baixe o arquivo .m3u e use “Escolher arquivo”, ou rode a EFTV localmente para importar por link."
      );
    }
    if (!resposta.ok) {
      throw new Error(`O servidor da playlist respondeu com HTTP ${resposta.status}.`);
    }
    const texto = await resposta.text();
    return adicionarTexto(texto, nomeDaUrl(url), url);
  }

  async function adicionarArquivo(file) {
    const texto = await file.text();
    const nome = file.name.replace(/\.(m3u8?)$/i, "").replace(/[_-]+/g, " ").trim() || "Playlist enviada";
    return adicionarTexto(texto, nome, "");
  }

  async function atualizar(id) {
    const playlists = await listar();
    const playlist = playlists.find((p) => p.id === id);
    if (!playlist) throw new Error("Playlist não encontrada.");
    if (!playlist.url) throw new Error("Esta playlist foi enviada como arquivo e não tem um link para atualizar.");
    const resultado = await adicionarUrl(playlist.url);
    // A importação criou uma playlist nova; remove a antiga para não duplicar.
    if (resultado.playlist && resultado.playlist.id !== id) {
      await removerDoBanco(id);
      await reconstruir();
    }
    return resultado;
  }

  async function remover(id) {
    await removerDoBanco(id);
    await reconstruir();
    return { message: "Playlist removida." };
  }

  async function limpar() {
    await limparBanco();
    await reconstruir();
    return { message: "Todas as playlists foram removidas." };
  }

  window.EFTVStatic = {
    listar,
    adicionarUrl,
    adicionarArquivo,
    atualizar,
    remover,
    limpar,
    reconstruir,
    resumir,
  };

  reconstruir().catch((erro) => {
    console.error("EFTV: falha ao carregar o armazenamento local.", erro);
    window.CANAIS_CATALOGO_PRONTO = true;
    window.CANAIS_STATIC_READY = true;
    document.dispatchEvent(new CustomEvent("eftv:catalogo-pronto"));
  });
})();
