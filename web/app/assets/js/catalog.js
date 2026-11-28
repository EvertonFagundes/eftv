/* ============================================================
   EFTV — Catálogo
   Carrega canais/categorias da API, da playlist licenciada ou do
   servidor local (modo self-hosted). Mantém fallback de demonstração.
   Espelha busca sem acento, filtros, categorias, "Abertos" e A-Z.
   ============================================================ */

(() => {
  "use strict";

  const store = window.EFTV_STORE;
  const playlist = window.EFTV_PLAYLIST;
  const source = window.EFTV_SOURCE;

  // Mesmas regras do FreeTv.kt: emissoras abertas + exclusões dos canais
  // pagos da mesma família. O grupo também pode marcar "aberto".
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

  // Conteúdo adulto: filtrado enquanto o ajuste estiver desligado.
  const ADULTO = ["adulto", "adult", "xxx", "porn", "sexy", "erótic", "erotic", "+18", "18+"];

  const ICONES_CATEGORIA = {
    todos: "📺",
    abertos: "📡",
    tv: "🏠",
    noticias: "🗞️",
    esportes: "⚽",
    filmes: "🎬",
    series: "📺",
    novelas: "🎭",
    infantil: "🧸",
    documentarios: "🌍",
    musica: "🎵",
    religiosos: "🙏",
    adultos: "🔞",
    outros: "📁",
    animes: "🎌",
    variedades: "🎪",
    "24h": "🕓",
    streaming: "📱",
  };

  const DEMO_CANAIS = [
    { id: 1, nome: "Globo", slug: "globo", grupo: "Canais | TV Aberta", categoria: "tv", aoVivo: true, tipo: "canal", logo: null, url: null },
    { id: 2, nome: "Record", slug: "record", grupo: "Canais | TV Aberta", categoria: "tv", aoVivo: true, tipo: "canal", logo: null, url: null },
    { id: 3, nome: "SBT", slug: "sbt", grupo: "Canais | TV Aberta", categoria: "tv", aoVivo: true, tipo: "canal", logo: null, url: null },
    { id: 4, nome: "Band", slug: "band", grupo: "Canais | TV Aberta", categoria: "tv", aoVivo: true, tipo: "canal", logo: null, url: null },
    { id: 5, nome: "RedeTV", slug: "redetv", grupo: "Canais | TV Aberta", categoria: "tv", aoVivo: true, tipo: "canal", logo: null, url: null },
    { id: 6, nome: "GloboNews", slug: "globonews", grupo: "Canais | Notícias", categoria: "noticias", aoVivo: true, tipo: "canal", logo: null, url: null },
    { id: 7, nome: "CNN Brasil", slug: "cnn-brasil", grupo: "Canais | Notícias", categoria: "noticias", aoVivo: true, tipo: "canal", logo: null, url: null },
    { id: 8, nome: "BandNews", slug: "bandnews", grupo: "Canais | Notícias", categoria: "noticias", aoVivo: true, tipo: "canal", logo: null, url: null },
    { id: 9, nome: "Sportv", slug: "sportv", grupo: "Canais | Esportes", categoria: "esportes", aoVivo: true, tipo: "canal", logo: null, url: null },
    { id: 10, nome: "Premiere", slug: "premiere", grupo: "Canais | Esportes", categoria: "esportes", aoVivo: true, tipo: "canal", logo: null, url: null },
    { id: 11, nome: "ESPN", slug: "espn", grupo: "Canais | Esportes", categoria: "esportes", aoVivo: true, tipo: "canal", logo: null, url: null },
    { id: 12, nome: "HBO", slug: "hbo", grupo: "Canais | Filmes", categoria: "filmes", aoVivo: true, tipo: "canal", logo: null, url: null },
    { id: 13, nome: "Telecine", slug: "telecine", grupo: "Canais | Filmes", categoria: "filmes", aoVivo: true, tipo: "canal", logo: null, url: null },
    { id: 14, nome: "Cartoon Network", slug: "cartoon-network", grupo: "Canais | Infantil", categoria: "infantil", aoVivo: true, tipo: "canal", logo: null, url: null },
    { id: 15, nome: "Discovery Kids", slug: "discovery-kids", grupo: "Canais | Infantil", categoria: "infantil", aoVivo: true, tipo: "canal", logo: null, url: null },
    { id: 16, nome: "Ação Total", slug: "acao-total", grupo: "Filmes | Ação", categoria: "filmes", aoVivo: false, tipo: "filme", logo: null, url: null },
    { id: 17, nome: "Comédia em Casa", slug: "comedia-em-casa", grupo: "Filmes | Comédia", categoria: "filmes", aoVivo: false, tipo: "filme", logo: null, url: null },
    { id: 18, nome: "Série Noir", slug: "serie-noir", grupo: "Séries | Drama", categoria: "series", aoVivo: false, tipo: "serie", logo: null, url: null },
    { id: 19, nome: "Mundo Selvagem", slug: "mundo-selvagem", grupo: "Documentários", categoria: "documentarios", aoVivo: false, tipo: "filme", logo: null, url: null },
    { id: 20, nome: "Anime Night", slug: "anime-night", grupo: "Séries | Anime", categoria: "anime", aoVivo: false, tipo: "serie", logo: null, url: null },
  ];

  const DEMO_CATEGORIAS = [
    { id: "todos", nome: "Todos", icone: "📺" },
    { id: "abertos", nome: "Abertos", icone: "📡" },
    { id: "tv", nome: "TV Aberta", icone: "🏠" },
    { id: "noticias", nome: "Notícias", icone: "🗞️" },
    { id: "esportes", nome: "Esportes", icone: "⚽" },
    { id: "filmes", nome: "Filmes", icone: "🎬" },
    { id: "series", nome: "Séries", icone: "📺" },
    { id: "infantil", nome: "Infantil", icone: "🧸" },
    { id: "documentarios", nome: "Documentários", icone: "🌍" },
    { id: "anime", nome: "Anime", icone: "🎌" },
  ];

  function normalizar(texto) {
    return String(texto || "")
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .toLowerCase()
      .trim();
  }

  function ehAberto(item) {
    const nome = normalizar(item && (item.nome || item.name));
    for (const regra of ABERTOS) {
      if (!nome.includes(normalizar(regra.nome))) continue;
      if (regra.exclui.some((termo) => nome.includes(normalizar(termo)))) continue;
      return true;
    }
    const grupo = normalizar(item && (item.grupo || item.group_title || item.group));
    return grupo.includes("aberto");
  }

  function ehAdulto(item) {
    if (item && (item.adulto || item.is_adult)) return true;
    const texto = normalizar((item.nome || "") + " " + (item.grupo || "") + " " + (item.categoria || ""));
    return ADULTO.some((a) => texto.includes(normalizar(a)));
  }

  function tipoDoCanalLocal(canal) {
    const categoria = normalizar(canal.categoria);
    if (["series", "novelas", "animes", "anime"].includes(categoria)) return "serie";
    if (canal.aoVivo) return "canal";
    return "filme";
  }

  function normalizarCanaisLocal(dados) {
    const categorias = [{ id: "todos", nome: "Todos", icone: "📺" }];
    const vistos = new Set(["todos"]);
    (dados.categorias || []).forEach((cat) => {
      const id = String(cat.id || cat.slug || "").trim();
      if (!id || vistos.has(id)) return;
      vistos.add(id);
      categorias.push({
        id,
        nome: cat.nome || cat.name || id,
        icone: cat.icone || cat.icon || ICONES_CATEGORIA[id] || "📺",
      });
    });

    const canais = (dados.canais || []).map((canal, indice) => {
      const categoria = String(canal.categoria || "outros");
      const tipo = tipoDoCanalLocal(canal);
      const nome = canal.nome || canal.name || "Canal " + (indice + 1);
      const slug = canal.slug || "local-" + indice;
      return {
        id: "l" + slug,
        nome,
        slug,
        grupo: canal.grupo || canal.group || "",
        categoria,
        aoVivo: tipo === "canal" || !!canal.aoVivo,
        tipo,
        streamType: null,
        adulto: categoria === "adultos" || ehAdulto({ nome, grupo: canal.grupo, categoria }),
        logo: canal.logo ? source.absoluta(canal.logo) : null,
        url: null,
        local: true,
      };
    });

    return { canais, categorias };
  }

  const catalog = {
    canais: [],
    categorias: [],
    carregado: false,
    demo: false,
    local: false,
    erro: null,
    erroPlaylist: null,
    erroLocal: null,
    fonte: null,
    _mapa: new Map(),

    async carregar(forcar = false) {
      // Usa cache local por 6h (igual ao app Android). O catálogo real fica
      // no IndexedDB porque pode ter dezenas de milhares de itens.
      let cache = await store.getCatalogCacheAsync();
      if (cache && cache.fonte === "local") {
        const estado = await source.detectar();
        if (!estado.disponivel) cache = null;
      }
      const seisHoras = 6 * 60 * 60 * 1000;
      if (
        !forcar &&
        cache &&
        cache.version === 3 &&
        cache.salvoEm &&
        !cache.demo &&
        Date.now() - cache.salvoEm < seisHoras &&
        Array.isArray(cache.canais) &&
        cache.canais.length
      ) {
        this.aplicar(
          cache.canais,
          cache.categorias,
          !!cache.demo,
          cache.fonte || "cache",
          !!cache.local
        );
        return this;
      }

      const cacheAnterior =
        cache && !cache.demo && Array.isArray(cache.canais) && cache.canais.length ? cache : null;
      this.erroPlaylist = null;
      this.erroLocal = null;
      let erro = null;

      try {
        const dados = await this._buscar();
        if (!dados || !dados.canais.length) throw new Error("O catálogo veio vazio.");
        this.aplicar(
          dados.canais,
          dados.categorias,
          false,
          dados.fonte,
          dados.fonte === "local"
        );
        await store.setCatalogCacheAsync({
          version: 3,
          fonte: dados.fonte,
          canais: this.canais,
          categorias: this.categorias,
          demo: false,
          local: this.local,
        });
        return this;
      } catch (e) {
        erro = e;
      }

      // Falha de rede não apaga o catálogo que já está no aparelho.
      if (cacheAnterior) {
        this.aplicar(
          cacheAnterior.canais,
          cacheAnterior.categorias,
          !!cacheAnterior.demo,
          cacheAnterior.fonte || "cache",
          !!cacheAnterior.local
        );
        this.erro = erro;
        return this;
      }

      this.erro = erro;
      if (window.EFTV_CONFIG.DEMO_FALLBACK) {
        this.usarDemo();
        store.setCatalogCache({
          canais: this.canais,
          categorias: this.categorias,
          demo: true,
        });
        return this;
      }
      throw erro;
    },

    /**
     * Modo self-hosted: carrega o catálogo magro do server.py sem login.
     * As URLs só são resolvidas em /api/canal quando o canal é aberto.
     */
    async carregarLocal() {
      try {
        const estado = await source.detectar();
        if (!estado.disponivel) return false;
        const dados = await source.catalogoLocal();
        if (!dados) return false;
        const normalizado = normalizarCanaisLocal(dados);
        if (!normalizado.canais.length) {
          this.erroLocal = new Error(
            "O servidor local respondeu, mas não tem playlists. Importe uma playlist na versão local."
          );
          return false;
        }
        this.aplicar(
          normalizado.canais,
          normalizado.categorias,
          false,
          "local",
          true
        );
        await store.setCatalogCacheAsync({
          version: 3,
          fonte: "local",
          canais: this.canais,
          categorias: this.categorias,
          demo: false,
          local: true,
        });
        return true;
      } catch (e) {
        this.erroLocal = e;
        return false;
      }
    },

    /**
     * Busca o catálogo real como o app Android:
     * 1. URL embutida no build (opcional, builds privados);
     * 2. URL licenciada entregue pelo backend em /player/playlist, baixada
     *    direto pelo navegador ou pelo proxy local (DoH/UA/Referer);
     * 3. texto da playlist entregue pelo backend em /player/playlist-text;
     * 4. catálogo magro do server.py local (self-hosted);
     * 5. catálogo centralizado de /channels.
     * A URL e o texto nunca são logados.
     */
    async _buscar() {
      const temSessao = !!store.getSession();
      const embutida = String(window.EFTV_CONFIG.PLAYLIST_URL || "").trim();

      if (embutida && playlist) {
        try {
          return await this._carregarPlaylistUrl(embutida, "playlist-embutida");
        } catch (e) {
          this.erroPlaylist = e;
        }
      }

      if (temSessao && playlist) {
        try {
          const acesso = await window.EFTV_API.playlistAcesso();
          const url = acesso && (acesso.playlist_url || acesso.playlistUrl);
          if (url) {
            try {
              return await this._carregarPlaylistUrl(url, "playlist");
            } catch (e) {
              // CORS/hotlink: o backend ainda pode entregar o texto.
              this.erroPlaylist = e;
            }
          }
        } catch (e) {
          this.erroPlaylist = e;
        }

        try {
          const texto = await window.EFTV_API.playlistTexto();
          if (typeof texto === "string" && texto.trim()) {
            const dados = this._montarPlaylistTexto(texto, "playlist");
            if (dados) return dados;
          }
        } catch (e) {
          this.erroPlaylist = e;
        }
      }

      // Servidor local (self-hosted) como fallback: catálogo magro, sem URLs.
      try {
        const local = await this.carregarLocal();
        if (local) {
          return {
            canais: this.canais,
            categorias: this.categorias,
            fonte: "local",
          };
        }
      } catch (_) {}

      // Fallback: catálogo centralizado da API (pode estar vazio hoje).
      const [categorias, canais] = await Promise.all([
        window.EFTV_API.categorias(true),
        window.EFTV_API.canaisTodas({ page_size: 100, include_adult: true }),
      ]);
      const lista = normalizarCanais(canais);
      if (!lista.length) {
        const detalhe = this.erroPlaylist
          ? ` Playlist: ${this.erroPlaylist.message}`
          : this.erroLocal
            ? ` Servidor local: ${this.erroLocal.message}`
            : "";
        throw new Error("O catálogo está vazio." + detalhe);
      }
      return {
        canais: lista,
        categorias: normalizarCategorias(categorias),
        fonte: "api",
      };
    },

    _montarPlaylistTexto(texto, fonte) {
      if (!playlist) return null;
      const itens = playlist.parse(texto);
      if (!itens.length) return null;
      const dados = playlist.montarCatalogo(itens);
      if (!dados.canais.length) return null;
      return { ...dados, fonte };
    },

    async _carregarPlaylistUrl(url, fonte) {
      let destino = String(url || "").trim();
      if (!/^https?:\/\//i.test(destino)) {
        throw new Error("O servidor entregou uma URL de playlist inválida.");
      }

      const estado = await source.detectar();
      const misto = location.protocol === "https:" && /^http:\/\//i.test(destino);
      if (misto && !estado.disponivel) {
        // Página HTTPS não baixa http:// (conteúdo misto). Tenta HTTPS.
        destino = destino.replace(/^http:/i, "https:");
      }

      const tentativas = [];
      const vistos = new Set();
      function adicionar(alvo, proxy, doh) {
        if (!alvo || vistos.has(alvo)) return;
        vistos.add(alvo);
        tentativas.push({ alvo, proxy, doh: !!doh });
      }

      // Em página HTTPS, o proxy same-origin é o único caminho para http://.
      if (misto && estado.disponivel) {
        adicionar(source.remotePlaylistUrl(destino, false), true, false);
        adicionar(source.remotePlaylistUrl(destino, true), true, true);
      }

      adicionar(destino, false, false);

      if (estado.disponivel && !misto) {
        adicionar(source.remotePlaylistUrl(destino, false), true, false);
        adicionar(source.remotePlaylistUrl(destino, true), true, true);
      }

      let ultimoErro = null;
      for (const tentativa of tentativas) {
        try {
          let resposta;
          try {
            resposta = await fetch(tentativa.alvo, {
              cache: "no-store",
              mode: "cors",
              redirect: "follow",
            });
          } catch (_) {
            throw new Error(
              tentativa.proxy
                ? "O proxy local não conseguiu baixar a playlist."
                : "O navegador não conseguiu baixar a playlist do provedor (CORS ou rede)."
            );
          }
          if (!resposta.ok) {
            throw new Error(`O provedor respondeu HTTP ${resposta.status} ao entregar a playlist.`);
          }

          const resultado = await playlist.parseResposta(resposta);
          if (!resultado.itens.length) {
            throw new Error(resultado.diagnostico || playlist.diagnosticar(resultado.amostra));
          }
          const dados = playlist.montarCatalogo(resultado.itens);
          if (!dados.canais.length) {
            throw new Error("A playlist não gerou canais reproduzíveis.");
          }
          return { ...dados, fonte };
        } catch (e) {
          ultimoErro = e;
        }
      }

      throw ultimoErro || new Error("Não foi possível baixar a playlist.");
    },

    aplicar(canais, categorias, demo, fonte, local) {
      this.canais = Array.isArray(canais) ? canais : [];
      this.categorias = Array.isArray(categorias) ? categorias : [];
      this.demo = !!demo;
      this.local = !!local;
      this.fonte = fonte || null;
      this.carregado = true;
      this._indexar();
    },

    _indexar() {
      this._mapa = new Map();
      this.canais.forEach((item) => {
        this._mapa.set(String(item.id), item);
        (item.episodios || []).forEach((ep) => this._mapa.set(String(ep.id), ep));
      });
    },

    // Usa os dados de demonstração imediatamente (sem tentar a API)
    usarDemo() {
      this.aplicar(DEMO_CANAIS.slice(), DEMO_CATEGORIAS.slice(), true, "demo", false);
      this.erro = null;
      return this;
    },

    limpar() {
      this.aplicar([], [], false, null, false);
      return this;
    },

    /**
     * Resolve a transmissão de um item do catálogo local sob demanda.
     * O catálogo magro não carrega URLs; /api/canal devolve as fontes já
     * apontando para /api/proxy (HLS contínuo + fallback TS quando aplicável).
     */
    async fonteLocal(slug) {
      const estado = await source.detectar();
      if (!estado.disponivel) throw new Error("O servidor local não está disponível.");
      const canal = await source.canalLocal(slug);
      if (!canal) throw new Error("Transmissão não encontrada no servidor local.");
      const fontes = (canal.fontes || []).filter((f) => f && f.url);
      if (!fontes.length) throw new Error("O servidor local não informou uma fonte para este canal.");
      const principal = fontes[0];
      const alternativa = fontes[1] || null;
      return {
        url: principal.url,
        tipo: principal.tipo || null,
        headers: null,
        fallbackUrl: principal.fallbackUrl || (alternativa && alternativa.url) || null,
        fallbackTipo: principal.fallbackTipo || (alternativa && alternativa.tipo) || null,
        canal,
      };
    },

    // ---------- Consultas ----------
    todos() {
      return this.canais.slice();
    },

    aoVivo() {
      return this.canais.filter((c) => c.aoVivo || c.tipo === "canal");
    },

    filmes() {
      return this.canais.filter((c) => c.tipo === "filme" || c.categoria === "filmes");
    },

    series() {
      return this.canais.filter((c) => c.tipo === "serie" || c.categoria === "series");
    },

    abertos() {
      return this.canais.filter((c) => c.categoria === "abertos" || ehAberto(c));
    },

    porCategoria(id) {
      if (!id || id === "todos") return this.todos();
      if (id === "abertos") return this.abertos();
      return this.canais.filter((c) => c.categoria === id);
    },

    buscar(termo) {
      const q = normalizar(termo);
      if (!q) return [];
      return this.canais.filter((c) => {
        const nome = normalizar(c.nome);
        const grupo = normalizar(c.grupo);
        return nome.includes(q) || grupo.includes(q);
      });
    },

    filtrar({ termo = "", categoria = "todos", incluirAdulto = false } = {}) {
      let lista = termo ? this.buscar(termo) : this.porCategoria(categoria);
      if (!incluirAdulto) lista = lista.filter((c) => !ehAdulto(c));
      return lista;
    },

    porId(id) {
      return this._mapa.get(String(id)) || null;
    },

    porSlug(slug) {
      return this.canais.find((c) => c.slug === slug) || null;
    },

    contagemCategoria(id, incluirAdulto = true) {
      let lista = this.porCategoria(id);
      if (!incluirAdulto) lista = lista.filter((c) => !ehAdulto(c));
      return lista.length;
    },

    // Índice A-Z dos canais ao vivo (para a barra lateral)
    indiceAZ(lista) {
      const letras = new Set();
      lista.forEach((c) => {
        const primeira = normalizar(c.nome).charAt(0).toUpperCase();
        if (/[A-Z]/.test(primeira)) letras.add(primeira);
      });
      return [...letras].sort();
    },

    // Primeiro índice de uma letra na lista (para pular)
    primeiroIndiceLetra(lista, letra) {
      return lista.findIndex((c) => normalizar(c.nome).charAt(0).toUpperCase() === letra);
    },
  };

  function normalizarCategorias(bruto) {
    if (!Array.isArray(bruto)) return DEMO_CATEGORIAS.slice();
    return bruto.map((c) => ({
      id: c.id ?? c.slug ?? c.name,
      slug: c.slug ?? null,
      nome: c.name ?? c.nome ?? "Categoria",
      icone: c.icon ?? c.icone ?? ICONES_CATEGORIA[c.id] ?? "📺",
      adulto: !!(c.is_adult ?? c.adulto),
    }));
  }

  function normalizarCanais(bruto) {
    const lista = Array.isArray(bruto) ? bruto : (bruto && bruto.channels) || [];
    return lista.map((c, i) => ({
      id: c.id ?? i,
      nome: c.name ?? c.nome ?? "Canal " + (i + 1),
      slug: c.slug ?? String(c.id ?? i),
      grupo: c.group_title ?? c.group ?? c.grupo ?? "",
      categoria: c.category_id ?? c.category ?? c.categoria ?? "tv",
      aoVivo: c.is_live ?? c.aoVivo ?? c.live ?? false,
      tipo: c.kind ?? c.tipo ?? (c.is_live ? "canal" : "filme"),
      streamType: c.stream_type ?? null,
      adulto: !!(c.is_adult ?? c.adulto),
      logo: c.logo ?? c.logo_url ?? null,
      url: c.stream_url ?? c.url ?? null,
    }));
  }

  catalog.normalizar = normalizar;
  catalog.ehAberto = ehAberto;
  catalog.ehAdulto = ehAdulto;

  window.EFTV_CATALOG = catalog;
})();
