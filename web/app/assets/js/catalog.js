/* ============================================================
   EFTV — Catálogo
   Carrega canais/categorias da API e mantém fallback de demonstração.
   Espelha busca sem acento, filtros, categorias, "Abertos" e A-Z.
   ============================================================ */

(() => {
  "use strict";

  const store = window.EFTV_STORE;
  const playlist = window.EFTV_PLAYLIST;

  // Canais abertos reconhecidos pelo nome (mesma ideia do FreeTv.kt)
  const ABERTOS = [
    "globo", "record", "sbt", "band", "redetv", "cultura", "tv brasil",
    "gazeta", "aparecida", "canção nova", "rede vida", "tv senado",
    "tv câmara", "tv justiça", "futura", "tv escola",
  ];

  // Conteúdo adulto: filtrado enquanto o ajuste estiver desligado.
  const ADULTO = ["adulto", "adult", "xxx", "porn", "sexy", "erótic", "erotic"];

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

  function ehAberto(nome) {
    const n = normalizar(nome);
    return ABERTOS.some((a) => n.includes(normalizar(a)));
  }

  function ehAdulto(item) {
    if (item && (item.adulto || item.is_adult)) return true;
    const texto = normalizar((item.nome || "") + " " + (item.grupo || "") + " " + (item.categoria || ""));
    return ADULTO.some((a) => texto.includes(normalizar(a)));
  }

  const catalog = {
    canais: [],
    categorias: [],
    carregado: false,
    demo: false,
    erro: null,
    erroPlaylist: null,
    fonte: null,
    _mapa: new Map(),

    async carregar(forcar = false) {
      // Usa cache local por 6h (igual ao app Android). O catálogo real fica
      // no IndexedDB porque pode ter dezenas de milhares de itens.
      const cache = await store.getCatalogCacheAsync();
      const seisHoras = 6 * 60 * 60 * 1000;
      if (
        !forcar &&
        cache &&
        cache.salvoEm &&
        !cache.demo &&
        Date.now() - cache.salvoEm < seisHoras &&
        Array.isArray(cache.canais) &&
        cache.canais.length
      ) {
        this.aplicar(cache.canais, cache.categorias, !!cache.demo, cache.fonte || "cache");
        return this;
      }

      const cacheAnterior =
        cache && !cache.demo && Array.isArray(cache.canais) && cache.canais.length ? cache : null;
      this.erroPlaylist = null;
      let erro = null;

      try {
        const dados = await this._buscar();
        if (!dados || !dados.canais.length) throw new Error("O catálogo veio vazio.");
        this.aplicar(dados.canais, dados.categorias, false, dados.fonte);
        await store.setCatalogCacheAsync({
          version: 2,
          fonte: dados.fonte,
          canais: this.canais,
          categorias: this.categorias,
          demo: false,
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
          cacheAnterior.fonte || "cache"
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
     * Busca o catálogo real como o app Android:
     * 1. URL embutida no build (opcional, builds privados);
     * 2. URL licenciada entregue pelo backend em /player/playlist, baixada
     *    direto pelo navegador (o IP do cliente pode alcançar o provedor
     *    mesmo quando o Render não alcança);
     * 3. texto da playlist entregue pelo backend em /player/playlist-text;
     * 4. catálogo centralizado de /channels.
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
            const itens = playlist.parse(texto);
            if (itens.length) {
              const dados = playlist.montarCatalogo(itens);
              if (dados.canais.length) return { ...dados, fonte: "playlist" };
            }
          }
        } catch (e) {
          this.erroPlaylist = e;
        }
      }

      // Fallback: catálogo centralizado da API (pode estar vazio hoje).
      const [categorias, canais] = await Promise.all([
        window.EFTV_API.categorias(true),
        window.EFTV_API.canaisTodas({ page_size: 100, include_adult: true }),
      ]);
      const lista = normalizarCanais(canais);
      if (!lista.length) {
        const detalhe = this.erroPlaylist
          ? ` Playlist: ${this.erroPlaylist.message}`
          : "";
        throw new Error("O catálogo está vazio." + detalhe);
      }
      return {
        canais: lista,
        categorias: normalizarCategorias(categorias),
        fonte: "api",
      };
    },

    async _carregarPlaylistUrl(url, fonte) {
      let destino = String(url || "").trim();
      if (!/^https?:\/\//i.test(destino)) {
        throw new Error("O servidor entregou uma URL de playlist inválida.");
      }
      // Página HTTPS não baixa http:// (conteúdo misto). Tenta HTTPS.
      if (location.protocol === "https:" && /^http:\/\//i.test(destino)) {
        destino = destino.replace(/^http:/i, "https:");
      }

      let resposta;
      try {
        resposta = await fetch(destino, {
          cache: "no-store",
          mode: "cors",
          redirect: "follow",
        });
      } catch (_) {
        throw new Error(
          "O navegador não conseguiu baixar a playlist do provedor (CORS ou rede)."
        );
      }
      if (!resposta.ok) {
        throw new Error(`O provedor respondeu HTTP ${resposta.status} ao entregar a playlist.`);
      }
      const texto = await resposta.text();
      const itens = playlist.parse(texto);
      if (!itens.length) throw new Error(playlist.diagnosticar(texto));
      const dados = playlist.montarCatalogo(itens);
      if (!dados.canais.length) {
        throw new Error("A playlist não gerou canais reproduzíveis.");
      }
      return { ...dados, fonte };
    },

    aplicar(canais, categorias, demo, fonte) {
      this.canais = Array.isArray(canais) ? canais : [];
      this.categorias = Array.isArray(categorias) ? categorias : [];
      this.demo = !!demo;
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
      this.aplicar(DEMO_CANAIS.slice(), DEMO_CATEGORIAS.slice(), true, "demo");
      this.erro = null;
      return this;
    },

    limpar() {
      this.aplicar([], [], false, null);
      return this;
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
      return this.canais.filter((c) => ehAberto(c.nome));
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

    contagemCategoria(id) {
      return this.porCategoria(id).length;
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
      icone: c.icon ?? c.icone ?? "📺",
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