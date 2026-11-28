/* ============================================================
   EFTV — Playlist M3U
   Importa a playlist licenciada pelo backend autenticado
   (/player/playlist-text), classifica canais/filmes/séries e
   agrupa episódios, como o app Android.

   O parser aceita leitura incremental (response.body) para listas
   grandes, #EXTVLCOPT/#EXTHTTP e headers no estilo Kodi
   (http://...|User-Agent=...&Referer=...).
   ============================================================ */

(() => {
  "use strict";

  const ATTR_REGEX = /([A-Za-z0-9_-]+)\s*=\s*"([^"]*)"/g;
  const INVALID_LOGOS = new Set(["xx", "xxx", "tvg-logo=", "null", "none", "-"]);
  // O Android importa centenas de milhares de itens em streaming. O navegador
  // não tem SQLite, mas 250 mil itens ainda cabem no IndexedDB da maioria dos
  // aparelhos; a grade continua renderizando em lotes de 240.
  const MAX_ITENS = 250000;
  const MAX_LINHAS = 4000000;
  const AMOSTRA_MAX = 8192;

  const LIVE_STRONG = ["canal", "canais", "ao vivo", "live", "24h", "24 horas", "ppv"];
  const SERIES_GROUP = [
    "serie", "series", "novela", "novelas", "anime", "animes",
    "dorama", "doramas", "sitcom", "sitcoms", "temporada", "temporadas",
  ];
  const MOVIE_GROUP = [
    "filme", "filmes", "movie", "movies", "cinema", "cinemas", "vod",
    "lancamento", "lancamentos", "legendado", "legendados",
    "dublado", "dublados", "oscar", "premiado", "premiados",
    "classico", "classicos",
  ];
  const GENRE_HINTS = [
    "acao", "comedia", "terror", "suspense", "drama", "romance",
    "ficcao", "aventura", "animacao", "guerra", "faroeste",
    "policial", "misterio", "fantasia", "familia",
  ];
  const LIVE_WEAK = [
    "esporte", "esportes", "noticia", "noticias", "aberto", "abertos",
    "religioso", "religiosos", "musica", "variedade", "variedades",
    "documentario", "documentarios", "infantil", "desenho", "desenhos",
  ];

  const SERIES_NAME = /(\bS\d{1,2}\s*E\d{1,4}\b|\b\d{1,2}x\d{1,3}\b|\b(?:ep|episodio|episode|cap|capitulo)\s*\.?\s*\d{1,4}\b|\btemporada\s*\d{1,2}\b)/i;
  const VOD_EXTENSION = /\.(mkv|mp4|avi|mov|wmv|flv|webm|m4v|3gp|mpg|mpeg)(?:$|\?)/i;

  const ADULTO = [
    "adulto", "adultos", "adult", "xxx", "+18", "18+", "porn",
    "erotic", "sensual", "sexy", "sexo",
  ];

  // Mesmas regras do FreeTv.kt (Android): nome da emissora + exclusões dos
  // canais pagos da mesma família. A categoria virtual também aceita itens
  // cujo grupo já contenha "aberto".
  const ABERTOS = [
    { nome: "globo", exclui: ["globonews", "globoplay", "premiere", "telecine", "canal globo"] },
    { nome: "record", exclui: [] },
    { nome: "sbt", exclui: [] },
    { nome: "band", exclui: ["bandsports", "band sports", "bandnews", "band news", "band play"] },
    { nome: "redetv", exclui: [] },
    { nome: "rede tv", exclui: [] },
    { nome: "cultura", exclui: [] },
    { nome: "tv brasil", exclui: [] },
    { nome: "gazeta", exclui: [] },
    { nome: "aparecida", exclui: [] },
    { nome: "cancaonova", exclui: [] },
    { nome: "canção nova", exclui: [] },
    { nome: "rede vida", exclui: [] },
    { nome: "loading", exclui: [] },
    { nome: "ideal tv", exclui: [] },
    { nome: "futura", exclui: [] },
    { nome: "tv senado", exclui: [] },
    { nome: "tv camara", exclui: [] },
    { nome: "tv justica", exclui: [] },
    { nome: "tv assembleia", exclui: [] },
    { nome: "record news", exclui: [] },
  ];

  const CATEGORIAS_INFO = [
    { id: "abertos", nome: "Abertos", icone: "📡" },
    { id: "tv", nome: "TV", icone: "🏠" },
    { id: "noticias", nome: "Notícias", icone: "🗞️" },
    { id: "esportes", nome: "Esportes", icone: "⚽" },
    { id: "filmes", nome: "Filmes", icone: "🎬" },
    { id: "series", nome: "Séries", icone: "📺" },
    { id: "infantil", nome: "Infantil", icone: "🧸" },
    { id: "documentarios", nome: "Documentários", icone: "🌍" },
    { id: "musica", nome: "Música", icone: "🎵" },
    { id: "religiosos", nome: "Religiosos", icone: "🙏" },
    { id: "adultos", nome: "Adultos", icone: "🔞" },
    { id: "outros", nome: "Outros", icone: "📁" },
  ];

  // A ordem importa: grupos mais específicos vêm antes de "canais"/"tv".
  const MAPA_CATEGORIA = [
    { id: "adultos", chaves: ADULTO },
    { id: "series", chaves: SERIES_GROUP },
    { id: "filmes", chaves: MOVIE_GROUP },
    { id: "esportes", chaves: ["esporte", "esportes", "sport", "sports", "ppv", "combate", "luta"] },
    { id: "noticias", chaves: ["noticia", "noticias", "news", "jornal"] },
    { id: "infantil", chaves: ["infantil", "crianca", "criancas", "kids", "cartoon", "desenho", "desenhos"] },
    { id: "documentarios", chaves: ["documentario", "documentarios", "documentary", "natureza", "historia"] },
    { id: "musica", chaves: ["musica", "musical", "music", "show", "shows", "clipe"] },
    { id: "religiosos", chaves: ["religioso", "religiosos", "religiao", "gospel", "igreja", "fe"] },
    { id: "abertos", chaves: ["aberto", "abertos", "aberta", "abertas", "open"] },
    { id: "tv", chaves: ["canais", "canal", "tv", "variedade", "variedades", "24h", "24 horas"] },
  ];

  const SEASON_EPISODE = /\b[st](\d{1,2})\s*[-_. ]?\s*e(\d{1,4})\b/i;
  const SEASON_WORD_EPISODE = /\b(?:temporada|temp|season)\s*\.?\s*(\d{1,2})\s*[-,._ ]*\s*(?:epis[oó]dio|episode|ep|cap[ií]tulo|cap|e)\s*\.?\s*(\d{1,4})\b/i;
  const CROSS = /\b(\d{1,2})x(\d{1,3})\b/i;
  const EPISODE_ONLY = /\b(?:epis[oó]dio|episode|ep|cap[ií]tulo|cap)\s*\.?\s*(\d{1,4})\b/i;
  const DASH_NUMBER = /^(.+?)\s+[-–]\s+(\d{1,4})$/;

  const LEADING_JUNK = /^[\s\-–—_.:|]+/;
  const TRAILING_JUNK = /[\s\-–—_.:|,(\[]+$/;
  const TRAILING_YEAR = /\s*[(\[]\s*(?:19|20)\d{2}\s*[)\]]\s*$/;
  const TRAILING_TAG = /(?:\s*\[[^\]]*\]|\s*\((?:fhd|hd|sd|4k|uhd|h\.?26[45]|hevc|\d{3,4}p)\)|(?:^|\s+)(?:fhd|hd|sd|4k|uhd|h\.?26[45]|hevc|\d{3,4}p))\s*$/i;
  const NON_ALNUM = /[^a-z0-9]+/g;

  function normalizar(texto) {
    return String(texto || "")
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .toLowerCase()
      .trim();
  }

  function hash(texto) {
    let h = 2166136261;
    const s = String(texto || "");
    for (let i = 0; i < s.length; i++) {
      h ^= s.charCodeAt(i);
      h = Math.imul(h, 16777619);
    }
    return (h >>> 0).toString(36);
  }

  function slugify(texto) {
    return normalizar(texto)
      .replace(NON_ALNUM, "-")
      .replace(/^-+|-+$/g, "")
      .slice(0, 64);
  }

  function nameAfterAttributes(line) {
    let inQuotes = false;
    for (let i = 0; i < line.length; i++) {
      const ch = line[i];
      if (ch === '"') inQuotes = !inQuotes;
      else if (ch === "," && !inQuotes) return line.substring(i + 1).trim();
    }
    return "";
  }

  function parseAttributes(line) {
    const attrs = {};
    const logos = [];
    ATTR_REGEX.lastIndex = 0;
    let m;
    while ((m = ATTR_REGEX.exec(line)) !== null) {
      const chave = m[1].toLowerCase();
      const valor = m[2].trim();
      attrs[chave] = valor;
      if (chave === "tvg-logo") logos.push(valor);
    }
    return { attrs, logos };
  }

  function isAbsoluteLogo(valor) {
    return /^(https?:)?\/\//i.test(valor) || /^data:image\//i.test(valor);
  }

  function escolherLogo(logos) {
    const limpos = logos.map((l) => l.trim()).filter(Boolean);
    const escolhido = [...limpos].reverse().find(isAbsoluteLogo) || limpos[limpos.length - 1] || "";
    let valor = escolhido.trim().replace(/^["']|["']$/g, "").replace(/&amp;/g, "&");
    if (!valor || INVALID_LOGOS.has(valor.toLowerCase())) return "";
    if (valor.startsWith("//")) valor = "https:" + valor;
    return valor;
  }

  function streamType(url, kodiType) {
    const u = String(url || "").toLowerCase();
    if (kodiType === "dash" || u.includes(".mpd")) return "dash";
    if (kodiType === "ts" || u.includes(".ts")) return "ts";
    if (/\.(mp4|mkv|avi|mov|webm|m4v)(?:$|\?)/.test(u)) return "mp4";
    return "hls";
  }

  function isPlayableUrl(url) {
    return /^https?:\/\//i.test(String(url || "").trim());
  }

  function classificar(group, name, url) {
    const g = normalizar(group);
    const n = normalizar(name);
    const u = String(url || "").toLowerCase();

    // Grupos específicos vêm antes de "canais": o provedor costuma usar
    // "Canais | Filmes" e "Canais | Séries".
    if (SERIES_GROUP.some((t) => g.includes(t))) return "serie";
    if (MOVIE_GROUP.some((t) => g.includes(t))) return "filme";
    if (LIVE_STRONG.some((t) => g.includes(t))) return "canal";

    if (SERIES_NAME.test(n)) return "serie";
    if (VOD_EXTENSION.test(u)) return "filme";
    if (n.includes("filme") || n.includes("movie")) return "filme";
    if (GENRE_HINTS.some((t) => g.includes(t))) return "filme";
    if (LIVE_WEAK.some((t) => g.includes(t))) return "canal";

    // HLS (.m3u8) pode ser ao vivo ou VOD; sem pistas, assume canal.
    return "canal";
  }

  function ehAdulto(group, name) {
    const texto = normalizar(String(group || "") + " " + String(name || ""));
    return ADULTO.some((t) => texto.includes(normalizar(t)));
  }

  function ehAberto(nome, grupo) {
    const n = normalizar(nome);
    for (const regra of ABERTOS) {
      if (!n.includes(normalizar(regra.nome))) continue;
      if (regra.exclui.some((termo) => n.includes(normalizar(termo)))) continue;
      return true;
    }
    return normalizar(grupo).includes("aberto");
  }

  function categoriaDoGrupo(group, tipo) {
    const g = normalizar(group);
    for (const mapa of MAPA_CATEGORIA) {
      if (mapa.chaves.some((chave) => g.includes(normalizar(chave)))) return mapa.id;
    }
    if (tipo === "filme") return "filmes";
    if (tipo === "serie") return "series";
    return "tv";
  }

  function limparTitulo(bruto) {
    let t = String(bruto || "").replace(LEADING_JUNK, "");
    t = t.replace(TRAILING_JUNK, "");
    t = t.replace(TRAILING_YEAR, "");
    t = t.replace(TRAILING_JUNK, "");
    return t.trim();
  }

  function limparTituloEpisodio(bruto) {
    let t = String(bruto || "").replace(LEADING_JUNK, "");
    for (let i = 0; i < 3; i++) {
      const proximo = t.replace(TRAILING_TAG, "");
      if (proximo === t) break;
      t = proximo;
    }
    t = t.replace(TRAILING_JUNK, "").trim();
    return t.length > 90 ? t.slice(0, 90).trimEnd() : t;
  }

  function chaveSerie(titulo) {
    const chave = normalizar(titulo).replace(NON_ALNUM, " ").trim();
    return chave || normalizar(titulo);
  }

  function finalizarSerie(titulo, temporada, episodio, tituloEpisodio) {
    const limpo = limparTitulo(titulo);
    if (!limpo) return null;
    return {
      title: limpo,
      key: chaveSerie(limpo),
      season: temporada,
      episode: episodio,
      episodeTitle: limparTituloEpisodio(tituloEpisodio),
    };
  }

  function parseSeries(name) {
    const texto = String(name || "").trim();
    if (!texto) return null;

    let m = SEASON_EPISODE.exec(texto);
    if (m) {
      return finalizarSerie(
        texto.slice(0, m.index),
        Number(m[1]),
        Number(m[2]),
        texto.slice(m.index + m[0].length)
      );
    }

    m = SEASON_WORD_EPISODE.exec(texto);
    if (m) {
      return finalizarSerie(
        texto.slice(0, m.index),
        Number(m[1]),
        Number(m[2]),
        texto.slice(m.index + m[0].length)
      );
    }

    m = CROSS.exec(texto);
    if (m) {
      return finalizarSerie(
        texto.slice(0, m.index),
        Number(m[1]),
        Number(m[2]),
        texto.slice(m.index + m[0].length)
      );
    }

    m = EPISODE_ONLY.exec(texto);
    if (m) {
      return finalizarSerie(
        texto.slice(0, m.index),
        1,
        Number(m[1]),
        texto.slice(m.index + m[0].length)
      );
    }

    m = DASH_NUMBER.exec(texto);
    if (m) {
      return finalizarSerie(m[1], 1, Number(m[2]), "");
    }

    return null;
  }

  function chaveHeader(nome) {
    const n = normalizar(nome).replace(/\s+/g, "-");
    if (n === "user-agent" || n === "useragent") return "User-Agent";
    if (n === "referer" || n === "referrer") return "Referer";
    if (n === "origin") return "Origin";
    if (n === "cookie") return "Cookie";
    if (n === "authorization") return "Authorization";
    return String(nome || "").trim();
  }

  function adicionarHeaders(destino, texto) {
    if (!texto) return;
    String(texto).split(/[&;]/).forEach((par) => {
      const igual = par.indexOf("=");
      if (igual <= 0) return;
      const chave = par.slice(0, igual).trim();
      const valor = par.slice(igual + 1).trim();
      if (chave && valor) destino[chaveHeader(chave)] = valor;
    });
  }

  /**
   * Separa headers embutidos na URL no estilo Kodi:
   * http://servidor/canal.m3u8|User-Agent=VLC&Referer=http://...
   */
  function separarUrlHeaders(linha) {
    const texto = String(linha || "").trim();
    const barra = texto.indexOf("|");
    if (barra < 0) return { url: texto, headers: null };
    const url = texto.slice(0, barra).trim();
    const headers = {};
    adicionarHeaders(headers, texto.slice(barra + 1));
    return { url, headers: Object.keys(headers).length ? headers : null };
  }

  function extrairHeadersExtvlc(line, headers) {
    const texto = line.substring(line.indexOf(":") + 1).trim();
    const igual = texto.indexOf("=");
    if (igual <= 0) return;
    const chave = normalizar(texto.slice(0, igual));
    const valor = texto.slice(igual + 1).trim();
    if (!valor) return;
    if (chave === "http-user-agent") headers["User-Agent"] = valor;
    else if (chave === "http-referrer" || chave === "http-referer") headers.Referer = valor;
    else if (chave === "http-origin") headers.Origin = valor;
    else if (chave === "http-cookie") headers.Cookie = valor;
    else if (chave === "http-header") adicionarHeaders(headers, valor);
  }

  /**
   * Cria um parser incremental. Cada linha é processada e descartada; os itens
   * prontos ficam em `itens`. Isso permite baixar uma M3U enorme sem manter o
   * texto inteiro na memória.
   */
  function criarParser(opcoes = {}) {
    const maxItens = Number(opcoes.maxItens) > 0 ? Number(opcoes.maxItens) : MAX_ITENS;
    const itens = [];
    let pending = null;
    let totalLinhas = 0;
    let amostra = "";
    let truncado = false;

    function processarLinha(bruta) {
      if (truncado) return;
      totalLinhas += 1;
      if (totalLinhas > MAX_LINHAS) {
        truncado = true;
        return;
      }
      const linhaOriginal = String(bruta == null ? "" : bruta);
      if (amostra.length < AMOSTRA_MAX) {
        amostra += linhaOriginal.slice(0, AMOSTRA_MAX - amostra.length) + "\n";
      }
      const line = linhaOriginal.trim();
      if (!line) return;

      if (/^#EXTINF/i.test(line)) {
        const { attrs, logos } = parseAttributes(line);
        const nome = nameAfterAttributes(line) || attrs["tvg-name"] || "Sem nome";
        pending = {
          name: nome,
          group: attrs["group-title"] || "Sem categoria",
          logo: escolherLogo(logos),
          tvgId: attrs["tvg-id"] || "",
          headers: {},
          kodiType: "",
        };
        return;
      }

      if (/^#EXTGRP/i.test(line)) {
        const grupo = line.substring(line.indexOf(":") + 1).trim();
        if (grupo && pending) pending.group = grupo;
        return;
      }

      if (/^#EXTVLCOPT/i.test(line)) {
        if (pending) extrairHeadersExtvlc(line, pending.headers);
        return;
      }

      if (/^#EXTHTTP/i.test(line)) {
        if (!pending) return;
        const json = line.substring(line.indexOf(":") + 1).trim();
        try {
          const dados = JSON.parse(json);
          Object.entries(dados || {}).forEach(([chave, valor]) => {
            if (valor != null && String(valor).trim()) {
              pending.headers[chaveHeader(chave)] = String(valor).trim();
            }
          });
        } catch (_) {}
        return;
      }

      if (/^#KODIPROP/i.test(line)) {
        if (!pending) return;
        const texto = line.substring(line.indexOf(":") + 1).trim();
        const igual = texto.indexOf("=");
        if (igual <= 0) return;
        const chave = normalizar(texto.slice(0, igual));
        const valor = texto.slice(igual + 1).trim();
        if (chave === "inputstream.adaptive.manifest_type" && valor) {
          pending.kodiType = valor.toLowerCase();
        } else if (chave === "inputstream.adaptive.stream_headers") {
          adicionarHeaders(pending.headers, valor);
        }
        return;
      }

      if (line.startsWith("#")) return;
      if (!pending) return;

      const separado = separarUrlHeaders(line);
      if (!isPlayableUrl(separado.url)) {
        pending = null;
        return;
      }

      const headers = { ...(pending.headers || {}), ...(separado.headers || {}) };
      const item = {
        name: pending.name,
        group: pending.group,
        logo: pending.logo,
        tvgId: pending.tvgId,
        url: separado.url,
        tipo: classificar(pending.group, pending.name, separado.url),
        streamType: streamType(separado.url, pending.kodiType),
      };
      if (Object.keys(headers).length) item.headers = headers;
      itens.push(item);
      pending = null;
      if (itens.length >= maxItens) truncado = true;
    }

    function finalizar() {
      return {
        itens,
        amostra,
        linhas: totalLinhas,
        truncado,
      };
    }

    return {
      processarLinha,
      finalizar,
      get itens() { return itens; },
      get truncado() { return truncado; },
      get linhas() { return totalLinhas; },
    };
  }

  function parseComTexto(texto, parser) {
    const p = parser || criarParser();
    const linhas = String(texto || "").replace(/^\uFEFF/, "").split(/\r?\n/);
    for (const linha of linhas) {
      p.processarLinha(linha);
      if (p.truncado) break;
    }
    return p.finalizar();
  }

  /**
   * Lê o texto M3U e devolve os itens crus (sem agrupar séries).
   * Só aceita URLs http(s): rtmp/udp/rtsp não tocam no navegador.
   */
  function parse(texto) {
    return parseComTexto(texto).itens;
  }

  /**
   * Lê uma Response (fetch) em streaming, sem carregar a playlist inteira.
   * Retorna { itens, amostra, linhas, truncado }.
   */
  async function parseResposta(resposta, opcoes = {}) {
    const parser = criarParser(opcoes);
    const corpo = resposta && resposta.body;
    const TextDecoderImpl = window.TextDecoder ||
      (typeof TextDecoder !== "undefined" ? TextDecoder : null);

    if (!corpo || typeof corpo.getReader !== "function" || !TextDecoderImpl) {
      const texto = await resposta.text();
      const resultado = parseComTexto(texto, parser);
      if (!resultado.itens.length) resultado.diagnostico = diagnosticar(texto);
      return resultado;
    }

    const reader = corpo.getReader();
    const decoder = new TextDecoderImpl("utf-8");
    let resto = "";
    let cancelado = false;

    try {
      while (!parser.truncado) {
        const { done, value } = await reader.read();
        if (done) break;
        resto += decoder.decode(value, { stream: true });
        let corte;
        while ((corte = resto.indexOf("\n")) >= 0) {
          const linha = resto.slice(0, corte).replace(/\r$/, "");
          resto = resto.slice(corte + 1);
          parser.processarLinha(linha);
          if (parser.truncado) break;
        }
      }
      if (!parser.truncado) {
        resto += decoder.decode();
        if (resto) parser.processarLinha(resto.replace(/\r$/, ""));
      }
    } finally {
      if (parser.truncado) {
        cancelado = true;
        try { await reader.cancel(); } catch (_) {}
      }
    }

    const resultado = parser.finalizar();
    resultado.cancelado = cancelado;
    if (!resultado.itens.length) resultado.diagnostico = diagnosticar(resultado.amostra);
    return resultado;
  }

  /**
   * Explica por que uma lista não gerou canais. Mesmas pistas do app Android,
   * para a pessoa saber se baixou a página errada do provedor.
   */
  function diagnosticar(texto) {
    const t = String(texto || "").replace(/^\uFEFF/, "").trim();
    if (!t) {
      return "O arquivo ou link está vazio. Escolha a playlist .m3u/.m3u8 completa do provedor.";
    }
    const inicio = t.slice(0, 2500);
    if (/^<!doctype\s+html|^<html[\s>]|<\?xml[^>]*>\s*<html/i.test(inicio) || /<html[\s>]/i.test(inicio)) {
      return "O link retornou uma página da web em vez da playlist. Copie o link M3U completo do provedor ou baixe o arquivo .m3u e importe pelo botão de arquivo.";
    }
    if (/<MPD[\s>]/i.test(inicio)) {
      return "O link retornou um manifesto DASH (.mpd), que não é uma lista de canais. Use o link M3U do provedor.";
    }
    if (/^[\[{]/.test(t)) {
      return "O link retornou JSON em vez de uma lista M3U. Use o endereço de playlist do provedor (get.php...type=m3u_plus).";
    }
    if (/#EXTINF/i.test(t)) {
      return "A lista tem canais declarados, mas nenhum endereço http(s) reproduzível foi encontrado. Verifique se o arquivo está completo e se os streams usam HTTP/HTTPS.";
    }
    return "O conteúdo não parece ser uma lista M3U/M3U8. Baixe o arquivo .m3u/.m3u8 completo do provedor e importe novamente.";
  }

  function montarCategorias(cards) {
    const contagem = new Map();
    cards.forEach((c) => {
      const id = c.categoria || "outros";
      contagem.set(id, (contagem.get(id) || 0) + 1);
    });

    const categorias = [{ id: "todos", nome: "Todos", icone: "📺" }];
    const abertos = cards.filter((c) => c.categoria === "abertos" || ehAberto(c.nome, c.grupo)).length;
    if (abertos > 0) {
      categorias.push({ id: "abertos", nome: "Abertos", icone: "📡", total: abertos });
    }

    CATEGORIAS_INFO.forEach((info) => {
      if (info.id === "abertos") return;
      const total = contagem.get(info.id) || 0;
      if (total > 0) categorias.push({ ...info, total });
    });

    return categorias;
  }

  function montarCatalogo(itens) {
    const cards = [];
    const series = new Map();
    const slugs = new Set();

    for (const item of itens) {
      const tipo = item.tipo === "canal" ? "canal" : item.tipo === "serie" ? "serie" : "filme";
      const adulto = ehAdulto(item.group, item.name);
      const base = {
        id: "p" + hash(item.url + "|" + item.name + "|" + item.group),
        nome: item.name,
        slug: slugify(item.name),
        grupo: item.group,
        categoria: categoriaDoGrupo(item.group, tipo),
        aoVivo: tipo === "canal",
        tipo,
        streamType: item.streamType,
        adulto,
        logo: item.logo || null,
        url: item.url,
      };
      if (item.headers && Object.keys(item.headers).length) base.headers = item.headers;

      if (tipo !== "serie") {
        cards.push(base);
        continue;
      }

      const info = parseSeries(item.name);
      if (!info) {
        // Grupo de série, mas nome sem marcador de episódio: fica solto e tocável.
        cards.push({ ...base, episodios: [] });
        continue;
      }

      let serie = series.get(info.key);
      if (!serie) {
        serie = {
          id: "s" + hash(info.key),
          nome: info.title,
          slug: slugify(info.title),
          grupo: item.group,
          categoria: "series",
          aoVivo: false,
          tipo: "serie",
          adulto,
          logo: item.logo || null,
          url: null,
          episodios: [],
        };
        series.set(info.key, serie);
      }

      const rotuloEpisodio = info.episodeTitle
        ? ` · ${info.episodeTitle}`
        : "";
      const episodio = {
        id: base.id,
        nome: `${serie.nome} — T${info.season} E${info.episode}${rotuloEpisodio}`,
        episodioTitulo: info.episodeTitle,
        temporada: info.season,
        episodio: info.episode,
        grupo: item.group,
        categoria: "series",
        tipo: "serie",
        aoVivo: false,
        streamType: item.streamType,
        adulto,
        logo: item.logo || serie.logo,
        url: item.url,
      };
      if (item.headers && Object.keys(item.headers).length) episodio.headers = item.headers;
      serie.episodios.push(episodio);
      if (!serie.logo && item.logo) serie.logo = item.logo;
    }

    for (const serie of series.values()) {
      serie.episodios.sort((a, b) => a.temporada - b.temporada || a.episodio - b.episodio);
      serie.temporadas = new Set(serie.episodios.map((e) => e.temporada)).size;
      serie.totalEpisodios = serie.episodios.length;
      if (!serie.logo) {
        const comLogo = serie.episodios.find((e) => e.logo);
        if (comLogo) serie.logo = comLogo.logo;
      }
      cards.push(serie);
    }

    // Slugs únicos e estáveis para deep links (?canal=slug).
    cards.forEach((card) => {
      let slug = card.slug || slugify(card.nome) || "item";
      if (slugs.has(slug)) slug = `${slug}-${String(card.id).slice(-4)}`;
      slugs.add(slug);
      card.slug = slug;
    });

    return {
      canais: cards,
      categorias: montarCategorias(cards),
    };
  }

  window.EFTV_PLAYLIST = {
    MAX_ITENS,
    parse,
    parseResposta,
    criarParser,
    diagnosticar,
    montarCatalogo,
    parseSeries,
    classificar,
    categoriaDoGrupo,
    ehAdulto,
    ehAberto,
    normalizar,
    hash,
    slugify,
    separarUrlHeaders,
  };
})();
