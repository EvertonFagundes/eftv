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

  function normalizarTexto(texto) {
    let t = String(texto || "");
    if (t.charCodeAt(0) === 0xfeff) t = t.slice(1);
    return t.replace(/\r\n?/g, "\n");
  }

  function decodificarBytes(bytes) {
    if (!bytes || !bytes.length) return "";
    if (bytes.length >= 2 && bytes[0] === 0xff && bytes[1] === 0xfe) {
      return new TextDecoder("utf-16le").decode(bytes.subarray(2));
    }
    if (bytes.length >= 2 && bytes[0] === 0xfe && bytes[1] === 0xff) {
      return new TextDecoder("utf-16be").decode(bytes.subarray(2));
    }
    if (bytes.length >= 3 && bytes[0] === 0xef && bytes[1] === 0xbb && bytes[2] === 0xbf) {
      return new TextDecoder("utf-8").decode(bytes.subarray(3));
    }
    return new TextDecoder("utf-8", { fatal: false }).decode(bytes);
  }

  function tipoCompactado(bytes) {
    if (!bytes || bytes.length < 2) return "";
    if (bytes[0] === 0x1f && bytes[1] === 0x8b) return "gzip";
    if (bytes.length >= 4 && bytes[0] === 0x50 && bytes[1] === 0x4b &&
        bytes[2] === 0x03 && bytes[3] === 0x04) {
      return "zip";
    }
    return "";
  }

  function limparUrl(linha) {
    return String(linha || "").trim().replace(/^["']+|["']+$/g, "").trim();
  }

  function extrairUrl(linha) {
    const v = limparUrl(linha);
    if (!v) return "";
    if (/^(https?:|data:|blob:)/i.test(v)) return v;
    if (v.startsWith("//")) return v;
    const achada = v.match(/https?:\/\/[^\s"'<>]+/i);
    if (achada) return achada[0];
    // Caminhos relativos só viram canais quando existe uma URL base.
    if (!/\s/.test(v) && /[/.]/.test(v)) return v;
    return "";
  }

  function esquemaDe(valor) {
    const v = String(valor || "").trim();
    if (v.startsWith("//")) return "//";
    const m = v.match(/^([a-z][a-z0-9+.-]*):/i);
    return m ? m[1].toLowerCase() : "";
  }

  function urlReproduzivel(valor) {
    return /^(https?:|data:|blob:)/i.test(String(valor || "").trim());
  }

  function tipoManifestoHls(texto) {
    const linhas = normalizarTexto(texto).split("\n");
    let master = false;
    let midia = false;
    for (const bruta of linhas) {
      const linha = bruta.trim();
      if (/^#EXT-X-STREAM-INF/i.test(linha)) master = true;
      else if (/^#EXT-X-(TARGETDURATION|MEDIA-SEQUENCE)/i.test(linha)) midia = true;
    }
    if (master) return "master";
    if (midia) return "midia";
    return "";
  }

  function diagnosticarPlaylist(texto, stats) {
    const t = normalizarTexto(texto).trim();
    if (!t) return "O arquivo ou link está vazio. Envie uma playlist .m3u/.m3u8 do provedor.";
    const inicio = t.slice(0, 2500);
    if (/^<!doctype\s+html|^<html[\s>]|<\?xml[^>]*>\s*<html/i.test(inicio) || /<html[\s>]/i.test(inicio)) {
      return "O link retornou uma página da web em vez de uma playlist. Copie o link M3U completo do provedor (geralmente termina em .m3u, .m3u8 ou contém get.php...type=m3u_plus) ou baixe o arquivo .m3u e use “Escolher arquivo”.";
    }
    if (/<MPD[\s>]/i.test(inicio)) {
      return "O link retornou um manifesto DASH (.mpd), que não é importado como playlist. Use o link M3U do provedor.";
    }
    if (/^[\[{]/.test(t)) {
      return "O link retornou dados JSON em vez de uma lista M3U. Use o link de playlist do provedor (get.php...type=m3u_plus), não o link da API.";
    }

    const esquemas = Object.keys(stats.esquemas || {});
    const naoSuportados = esquemas.filter((s) => !["http", "https", "data", "blob"].includes(s));
    if (naoSuportados.length) {
      const lista = naoSuportados.map((s) => s + "://").join(", ");
      return `A playlist usa links ${lista}, que não tocam no navegador. Use uma lista com links HTTP/HTTPS (HLS) do provedor.`;
    }
    if (stats.protocoloRelativo) {
      return "A playlist usa endereços relativos (//...). Importe pelo link original da playlist para que a EFTV complete os endereços.";
    }
    if (stats.relativos) {
      return "A playlist usa endereços relativos (sem http:// ou https://). Importe pelo link original do provedor ou use uma lista com endereços completos.";
    }
    if (stats.extinf > 0) {
      const qtd = stats.extinf.toLocaleString("pt-BR");
      return `A playlist declara ${qtd} ${stats.extinf === 1 ? "canal" : "canais"}, mas nenhum endereço de stream reconhecível foi encontrado. Verifique se o arquivo está completo e se os links usam HTTP/HTTPS.`;
    }
    return "O conteúdo não parece ser uma playlist M3U/M3U8 com canais. Use o arquivo .m3u/.m3u8 completo do provedor ou o link M3U correto.";
  }

  function parsePlaylist(texto, nome, url) {
    const normalizado = normalizarTexto(texto);
    const linhas = normalizado.split("\n");
    const canais = [];
    const stats = {
      extinf: 0,
      linhasUrl: 0,
      aceitos: 0,
      invalidos: 0,
      relativos: 0,
      protocoloRelativo: 0,
      esquemas: {},
    };
    let pendente = null;
    let truncada = false;
    const manifesto = tipoManifestoHls(normalizado);

    if (manifesto) {
      if (url) {
        canais.push({ name: nome || nomeDaUrl(url), group: "", logo: "", url });
      } else if (manifesto === "master") {
        const absoluta = linhas
          .filter((l) => !l.trim().startsWith("#"))
          .map(extrairUrl)
          .find((v) => /^https?:\/\//i.test(v));
        if (absoluta) {
          canais.push({
            name: nome || nomeDaUrl(absoluta),
            group: "",
            logo: "",
            url: absoluta,
          });
        } else {
          throw new Error(
            "Este arquivo é um manifesto HLS de um canal e usa endereços relativos. " +
              "Envie a playlist completa do provedor (.m3u/.m3u8 com vários #EXTINF) ou importe o link original do canal."
          );
        }
      } else {
        throw new Error(
          "Este arquivo é a lista de segmentos de um único canal HLS, não uma playlist de canais. " +
            "Importe o link original .m3u8 ou a playlist completa do provedor."
        );
      }
      return { channels: canais, truncated: false, stats };
    }

    for (const bruta of linhas) {
      const linha = bruta.trim();
      if (!linha) continue;

      if (/^#EXTINF/i.test(linha)) {
        stats.extinf += 1;
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

      if (/^#EXTGRP:/i.test(linha)) {
        if (pendente && !pendente.group) pendente.group = linha.slice(8).trim();
        continue;
      }

      if (linha.startsWith("#")) continue;

      const brutaUrl = extrairUrl(linha);
      if (!brutaUrl) {
        stats.invalidos += 1;
        continue;
      }
      stats.linhasUrl += 1;

      const esquema = esquemaDe(brutaUrl);
      if (esquema === "//") {
        stats.protocoloRelativo += 1;
      } else if (esquema) {
        stats.esquemas[esquema] = (stats.esquemas[esquema] || 0) + 1;
      } else {
        stats.relativos += 1;
      }

      const endereco = resolverUrl(brutaUrl, url);
      if (!urlReproduzivel(endereco)) continue;

      canais.push({
        name: (pendente && pendente.name) || endereco.split("/").pop() || `Canal ${canais.length + 1}`,
        group: (pendente && pendente.group) || "",
        logo: (pendente && pendente.logo) || "",
        url: endereco,
      });
      stats.aceitos += 1;
      pendente = null;

      if (canais.length >= MAX_CHANNELS) {
        truncada = true;
        break;
      }
    }

    return { channels: canais, truncated: truncada, stats };
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
    const { channels, truncated, stats } = parsePlaylist(texto, nome, url);
    if (!channels.length) {
      throw new Error(diagnosticarPlaylist(texto, stats));
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
    const original = String(url || "").trim();
    let destino = original;

    // Uma página HTTPS não consegue baixar http:// (conteúdo misto). Quando o
    // provedor também atende em HTTPS, tenta esse endereço automaticamente.
    if (window.location && window.location.protocol === "https:" && /^http:\/\//i.test(destino)) {
      destino = destino.replace(/^http:/i, "https:");
    }

    let resposta;
    try {
      resposta = await fetch(destino, { cache: "no-store", mode: "cors", redirect: "follow" });
    } catch (_) {
      if (destino !== original) {
        throw new Error(
          "O link usa HTTP, mas a página está em HTTPS. O navegador bloqueia esse download. " +
            "Use o mesmo link com https:// (se o provedor oferecer) ou baixe o arquivo .m3u e use “Escolher arquivo”."
        );
      }
      throw new Error(
        "O navegador não conseguiu baixar a playlist por CORS. No GitHub Pages não há proxy: baixe o arquivo .m3u e use “Escolher arquivo”, ou rode a EFTV localmente para importar por link."
      );
    }
    if (!resposta.ok) {
      if (destino !== original) {
        throw new Error(
          `O link HTTPS respondeu HTTP ${resposta.status}. O link original usa HTTP, que o navegador bloqueia em uma página HTTPS. ` +
            "Verifique se o provedor oferece HTTPS ou envie o arquivo .m3u."
        );
      }
      throw new Error(`O servidor da playlist respondeu com HTTP ${resposta.status}.`);
    }

    const bytes = new Uint8Array(await resposta.arrayBuffer());
    const compactado = tipoCompactado(bytes);
    if (compactado) {
      throw new Error(
        `O link retornou um arquivo compactado (${compactado}). Baixe e extraia o .m3u/.m3u8 antes de importar.`
      );
    }
    const texto = decodificarBytes(bytes);
    return adicionarTexto(texto, nomeDaUrl(destino), destino);
  }

  async function adicionarArquivo(file) {
    const nomeBase = (file && file.name) || "Playlist";
    let texto = "";
    if (file && typeof file.arrayBuffer === "function") {
      const bytes = new Uint8Array(await file.arrayBuffer());
      const compactado = tipoCompactado(bytes);
      if (compactado) {
        throw new Error(
          `O arquivo está compactado (${compactado}). Extraia o .m3u/.m3u8 antes de importar.`
        );
      }
      texto = decodificarBytes(bytes);
    } else {
      texto = await file.text();
    }
    const nome = nomeBase.replace(/\.(m3u8?)$/i, "").replace(/[_-]+/g, " ").trim() || "Playlist enviada";
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
