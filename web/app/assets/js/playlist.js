/* ============================================================
   EFTV — Playlist M3U
   Importa a playlist licenciada pelo backend autenticado
   (/player/playlist-text), classifica canais/filmes/séries e
   agrupa episódios, como o app Android.
   ============================================================ */

(() => {
  "use strict";

  const ATTR_REGEX = /([A-Za-z0-9_-]+)\s*=\s*"([^"]*)"/g;
  const INVALID_LOGOS = new Set(["xx", "xxx", "tvg-logo=", "null", "none", "-"]);
  // Mesmo teto do app Android: evita travar o navegador com listas gigantes.
  const MAX_ITENS = 50000;

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

  const ABERTOS = [
    "globo", "record", "sbt", "band", "redetv", "cultura", "tv brasil",
    "gazeta", "aparecida", "cancao nova", "rede vida", "tv senado",
    "tv camara", "tv justica", "futura", "tv escola",
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

  function streamType(url) {
    const u = String(url || "").toLowerCase();
    if (u.includes(".mpd")) return "dash";
    if (u.includes(".ts")) return "ts";
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

    if (LIVE_STRONG.some((t) => g.includes(t))) return "canal";
    if (SERIES_GROUP.some((t) => g.includes(t))) return "serie";
    if (MOVIE_GROUP.some((t) => g.includes(t))) return "filme";

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

  function ehAberto(nome) {
    const n = normalizar(nome);
    return ABERTOS.some((t) => n.includes(normalizar(t)));
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

  /**
   * Lê o texto M3U e devolve os itens crus (sem agrupar séries).
   * Só aceita URLs http(s): rtmp/udp/rtsp não tocam no navegador.
   */
  function parse(texto) {
    const itens = [];
    let pending = null;
    const linhas = String(texto || "").replace(/^\uFEFF/, "").split(/\r?\n/);

    for (const bruta of linhas) {
      const line = bruta.trim();
      if (!line) continue;

      if (/^#EXTINF/i.test(line)) {
        const { attrs, logos } = parseAttributes(line);
        const nome = nameAfterAttributes(line) || attrs["tvg-name"] || "Sem nome";
        pending = {
          name: nome,
          group: attrs["group-title"] || "Sem categoria",
          logo: escolherLogo(logos),
          tvgId: attrs["tvg-id"] || "",
        };
        continue;
      }

      if (/^#EXTGRP/i.test(line)) {
        const grupo = line.substring(line.indexOf(":") + 1).trim();
        if (grupo && pending) pending.group = grupo;
        continue;
      }

      if (line.startsWith("#")) continue;

      if (!pending) continue;
      if (!isPlayableUrl(line)) {
        pending = null;
        continue;
      }

      const item = pending;
      item.url = line;
      item.tipo = classificar(item.group, item.name, item.url);
      item.streamType = streamType(item.url);
      itens.push(item);
      pending = null;
      if (itens.length >= MAX_ITENS) break;
    }

    return itens;
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
    const abertos = cards.filter((c) => ehAberto(c.nome)).length;
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
      serie.episodios.push({
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
      });
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
  };
})();
