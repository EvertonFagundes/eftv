/* ============================================================
   EFTV — Controlador principal da versão web/PWA
   Router, catálogo, busca, A-Z, favoritos, recentes, progresso,
   conta, ajustes, player, auth, TV code e modo demo.
   ============================================================ */

(() => {
  "use strict";

  const cfg = window.EFTV_CONFIG;
  const store = window.EFTV_STORE;
  const api = window.EFTV_API;
  const catalog = window.EFTV_CATALOG;
  const player = window.EFTV_PLAYER;
  // Listas reais podem ter dezenas de milhares de canais. A grade mostra um
  // lote por vez (como no app Android) para não travar o navegador.
  const LIMITE_GRADE = 240;

  /* ------------------------------------------------------------------
     Estado
  ------------------------------------------------------------------ */
  const state = {
    usuario: null,
    assinatura: null,
    view: "ao-vivo",
    termo: "",
    categoriaAtual: "todos",
    demo: false,
    catalogError: null,
    carregando: false,
    playerItem: null,
    playerSessao: null,
    favoritos: store.getFavorites(),
    settings: store.getSettings(),
    ultimoProgressoSalvo: 0,
    buscaTimer: null,
    limiteGrade: LIMITE_GRADE,
  };

  /* ------------------------------------------------------------------
     Helpers
  ------------------------------------------------------------------ */
  const $ = (sel, raiz = document) => raiz.querySelector(sel);
  const $$ = (sel, raiz = document) => [...raiz.querySelectorAll(sel)];

  function fmtTempo(seg) {
    if (!Number.isFinite(seg) || seg < 0) return "0:00";
    const h = Math.floor(seg / 3600);
    const m = Math.floor((seg % 3600) / 60);
    const s = Math.floor(seg % 60);
    return h > 0
      ? `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`
      : `${m}:${String(s).padStart(2, "0")}`;
  }

  function normalizar(t) {
    return String(t || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
  }

  function formatarPreco(plano) {
    const centavos = plano.price_cents ?? plano.priceCents ?? plano.amount_cents;
    const valor = centavos != null ? Number(centavos) / 100 : plano.preco ?? plano.price ?? plano.amount;
    if (valor == null) return "R$ 19,90/mês";
    const numero = Number(valor);
    const reais = Number.isFinite(numero) ? (centavos == null && numero > 1000 ? numero / 100 : numero) : null;
    if (reais == null) return String(valor);
    return reais.toLocaleString("pt-BR", { style: "currency", currency: "BRL" }) +
      (plano.interval === "year" ? "/ano" : "/mês");
  }

  function hueDoNome(nome) {
    let h = 0;
    for (let i = 0; i < nome.length; i++) h = (h * 31 + nome.charCodeAt(i)) % 360;
    return h;
  }

  function mostrarToast(msg, ms = 2600) {
    const el = $("#toast");
    if (!el) return;
    el.textContent = msg;
    el.classList.remove("hidden");
    clearTimeout(el._timer);
    el._timer = setTimeout(() => el.classList.add("hidden"), ms);
  }

  function escapeHtml(t) {
    const d = document.createElement("div");
    d.textContent = String(t ?? "");
    return d.innerHTML;
  }

  function tipoStream(item) {
    const url = (item.url || "").toLowerCase();
    if (url.includes(".mpd")) return "dash";
    if (url.includes(".ts")) return "ts";
    if (url.includes(".mp4")) return "mp4";
    return "hls";
  }

  /* ------------------------------------------------------------------
     Router
  ------------------------------------------------------------------ */
  const rotas = [
    "ao-vivo", "filmes", "series", "categorias", "categoria",
    "favoritos", "continuar", "recentes", "conta", "ajustes", "ajuda", "busca",
  ];

  function navegar(view, opcoes = {}) {
    if (!rotas.includes(view)) view = "ao-vivo";

    $$(".view").forEach((v) => v.classList.add("hidden"));
    const alvo = $(`#view-${view}`);
    if (alvo) alvo.classList.remove("hidden");

    $$(".nav-link").forEach((l) => {
      l.classList.toggle("active", l.dataset.view === view);
    });

    const viewAnterior = state.view;
    state.view = view;
    if (viewAnterior !== view) state.limiteGrade = LIMITE_GRADE;
    fecharSidebar();

    if (opcoes.hash !== false) {
      const hash = view === "categoria" ? "categorias" : view;
      try {
        if (location.hash !== "#" + hash) history.replaceState(null, "", "#" + hash);
      } catch (_) {
        location.hash = hash;
      }
    }

    // Renderiza a view
    switch (view) {
      case "ao-vivo": renderAoVivo(); break;
      case "filmes": renderFilmes(); break;
      case "series": renderSeries(); break;
      case "categorias": renderCategorias(); break;
      case "favoritos": renderFavoritos(); break;
      case "continuar": renderContinuar(); break;
      case "recentes": renderRecentes(); break;
      case "busca": renderBusca(state.termo); break;
      case "conta": carregarConta(); break;
      case "ajustes": renderAjustes(); break;
      case "ajuda": renderAjuda(); break;
    }
  }

  function rotaDoHash() {
    const h = (location.hash || "#ao-vivo").slice(1);
    return rotas.includes(h) ? h : "ao-vivo";
  }

  /* ------------------------------------------------------------------
     Cards
  ------------------------------------------------------------------ */
  function criarCard(item, opcoes = {}) {
    const el = document.createElement("article");
    el.className = "item-card";
    el.dataset.id = item.id;
    el.dataset.letra = (normalizar(item.nome).charAt(0) || "").toUpperCase();
    el.tabIndex = 0;
    el.title = item.nome + (item.grupo ? " — " + item.grupo : "");

    const fav = state.favoritos.has(String(item.id));
    const progresso = opcoes.progresso || 0;
    const hue = hueDoNome(item.nome);

    el.innerHTML = `
      <div class="item-thumb" style="--hue:${hue}" data-name="${escapeHtml(item.nome)}">
        ${item.aoVivo ? '<span class="item-badge-live">AO VIVO</span>' : ""}
        ${fav ? '<span class="item-badge-fav">★</span>' : ""}
        ${progresso > 0 ? `<span class="item-progress"><i style="width:${Math.min(100, progresso)}%"></i></span>` : ""}
      </div>
      <div class="item-footer">
        <div class="item-info">
          <span class="item-grupo">${escapeHtml(item.grupo || "Canal")}</span>
        </div>
        <button class="btn-fav-small ${fav ? "active" : ""}" data-fav="${item.id}" aria-label="Favoritar">${fav ? "★" : "☆"}</button>
      </div>
    `;

    // Logo/capa real do provedor; se falhar, fica o gradiente com o nome.
    if (item.logo) {
      const thumb = el.querySelector(".item-thumb");
      const img = document.createElement("img");
      img.className = "item-logo";
      img.src = item.logo;
      img.alt = "";
      img.loading = "lazy";
      img.decoding = "async";
      img.referrerPolicy = "no-referrer";
      img.addEventListener("error", () => img.remove(), { once: true });
      thumb.appendChild(img);
    }

    el.addEventListener("click", (e) => {
      if (e.target.closest(".btn-fav-small")) return;
      abrirPlayer(item);
    });
    el.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        abrirPlayer(item);
      }
    });

    const btnFav = el.querySelector(".btn-fav-small");
    btnFav.addEventListener("click", (e) => {
      e.stopPropagation();
      toggleFavorito(item.id);
      const agora = state.favoritos.has(String(item.id));
      btnFav.textContent = agora ? "★" : "☆";
      btnFav.classList.toggle("active", agora);
      const badge = el.querySelector(".item-badge-fav");
      if (agora && !badge) {
        const span = document.createElement("span");
        span.className = "item-badge-fav";
        span.textContent = "★";
        el.querySelector(".item-thumb").appendChild(span);
      } else if (!agora && badge) {
        badge.remove();
      }
    });

    return el;
  }

  function preencherGrid(grid, itens, opcoes = {}) {
    const limite = Math.max(LIMITE_GRADE, Number(state.limiteGrade) || LIMITE_GRADE);
    const visiveis = itens.slice(0, limite);
    grid.innerHTML = "";
    visiveis.forEach((item) => grid.appendChild(criarCard(item, opcoes)));

    const view = grid.closest(".view") || grid.parentElement;
    const antigo = view ? view.querySelector(".btn-mais-grade") : null;
    if (antigo) antigo.remove();

    if (itens.length > visiveis.length && view) {
      const restantes = itens.length - visiveis.length;
      const botao = document.createElement("button");
      botao.type = "button";
      botao.className = "btn btn-outline btn-mais-grade";
      botao.textContent = `Mostrar mais (${restantes.toLocaleString("pt-BR")} restantes)`;
      botao.addEventListener("click", () => {
        state.limiteGrade += LIMITE_GRADE;
        if (typeof opcoes.aoMais === "function") opcoes.aoMais();
      });
      const alvo = grid.closest(".content-with-az") || grid;
      alvo.insertAdjacentElement("afterend", botao);
    }
  }

  function toggleFavorito(id) {
    const chave = String(id);
    if (state.favoritos.has(chave)) state.favoritos.delete(chave);
    else state.favoritos.add(chave);
    store.setFavorites(state.favoritos);
    if (state.view === "favoritos") renderFavoritos();
  }

  /* ------------------------------------------------------------------
     Views
  ------------------------------------------------------------------ */
  function canaisFiltrados() {
    return catalog.filtrar({
      categoria: state.categoriaAtual,
      incluirAdulto: state.settings.adulto,
    });
  }

  function renderAoVivo() {
    const grid = $("#grid-ao-vivo");
    const chips = $("#chips-ao-vivo");
    const vazio = $("#empty-ao-vivo");

    // Chips: usa as categorias que realmente vieram na playlist do provedor,
    // em vez de uma lista fixa que esconderia parte do catálogo real.
    chips.innerHTML = "";
    const categorias = (catalog.categorias || []).filter(
      (c) => c.id !== "adultos" || state.settings.adulto
    );
    if (state.categoriaAtual !== "todos" && !categorias.some((c) => c.id === state.categoriaAtual)) {
      state.categoriaAtual = "todos";
    }
    categorias.forEach((cat) => {
      const b = document.createElement("button");
      b.className = "chip" + (state.categoriaAtual === cat.id ? " active" : "");
      b.textContent = `${cat.icone || "📺"} ${cat.nome}`;
      b.addEventListener("click", () => {
        state.categoriaAtual = cat.id;
        state.limiteGrade = LIMITE_GRADE;
        renderAoVivo();
      });
      chips.appendChild(b);
    });

    let itens = canaisFiltrados().filter((c) => c.aoVivo || c.tipo === "canal");
    itens.sort((a, b) => a.nome.localeCompare(b.nome, "pt-BR"));
    preencherGrid(grid, itens, { aoMais: renderAoVivo });
    renderCatalogoAviso(itens);
    vazio.classList.toggle("hidden", itens.length > 0 || !!state.catalogError);

    renderAZ(itens.slice(0, state.limiteGrade));
  }

  function renderCatalogoAviso(itens) {
    const alerta = $("#catalog-alert");
    if (!alerta) return;

    alerta.classList.remove("erro");
    alerta.innerHTML = "";

    if (state.demo) {
      alerta.innerHTML = `
        <span><strong>Modo demonstração.</strong> Os canais exibidos são exemplos. Entre na sua conta para carregar os canais reais automaticamente.</span>
        <button type="button" class="btn-mini" id="btn-demo-entrar">Entrar</button>
      `;
      alerta.classList.remove("hidden");
      const entrar = $("#btn-demo-entrar");
      if (entrar) entrar.addEventListener("click", () => abrirAuth("login"));
      return;
    }

    if (!itens.length && state.catalogError) {
      alerta.classList.add("erro");
      alerta.innerHTML = `
        <span><strong>Não foi possível carregar os canais reais.</strong> ${escapeHtml(state.catalogError)}</span>
        <button type="button" class="btn-mini" id="btn-catalog-retry">Tentar novamente</button>
      `;
      alerta.classList.remove("hidden");
      const tentar = $("#btn-catalog-retry");
      if (tentar) {
        tentar.addEventListener("click", async () => {
          tentar.disabled = true;
          tentar.textContent = "Tentando...";
          await carregarCatalogo(true);
          renderAoVivo();
        });
      }
      return;
    }

    alerta.classList.add("hidden");
  }

  function renderAZ(itens) {
    const barra = $("#az-bar");
    if (!barra) return;
    barra.innerHTML = "";
    const letras = catalog.indiceAZ(itens);
    if (letras.length < 8) { barra.classList.add("hidden"); return; }
    barra.classList.remove("hidden");
    letras.forEach((letra) => {
      const b = document.createElement("button");
      b.textContent = letra;
      b.addEventListener("click", () => {
        const card = $(`#grid-ao-vivo .item-card[data-letra="${letra}"]`);
        if (card) card.scrollIntoView({ block: "center", behavior: "smooth" });
      });
      barra.appendChild(b);
    });
  }

  function renderFilmes() {
    const grid = $("#grid-filmes");
    const vazio = $("#empty-filmes");
    const itens = catalog.filtrar({ incluirAdulto: state.settings.adulto })
      .filter((c) => c.tipo === "filme" || c.categoria === "filmes");
    preencherGrid(grid, itens, { aoMais: renderFilmes });
    vazio.classList.toggle("hidden", itens.length > 0);
  }

  function renderSeries() {
    const grid = $("#grid-series");
    const vazio = $("#empty-series");
    const itens = catalog.filtrar({ incluirAdulto: state.settings.adulto })
      .filter((c) => c.tipo === "serie" || c.categoria === "series");
    preencherGrid(grid, itens, { aoMais: renderSeries });
    vazio.classList.toggle("hidden", itens.length > 0);
  }

  function renderCategorias() {
    const grid = $("#grid-categorias");
    grid.innerHTML = "";
    catalog.categorias.forEach((cat) => {
      if (cat.id === "todos") return;
      const qtd = catalog.contagemCategoria(cat.id);
      if (qtd === 0) return;
      const el = document.createElement("button");
      el.className = "categoria-card";
      el.innerHTML = `
        <span class="cat-icone">${cat.icone || "📺"}</span>
        <span class="cat-nome">${escapeHtml(cat.nome)}</span>
        <span class="cat-qtd">${qtd} ${qtd === 1 ? "item" : "itens"}</span>
      `;
      el.addEventListener("click", () => abrirCategoria(cat));
      grid.appendChild(el);
    });
  }

  function abrirCategoria(cat) {
    const grid = $("#grid-categoria");
    const titulo = $("#titulo-categoria");
    titulo.textContent = `${cat.icone || "📺"} ${cat.nome}`;
    const itens = catalog.filtrar({ categoria: cat.id, incluirAdulto: state.settings.adulto });
    const mesmaView = state.view === "categoria";
    navegar("categoria");
    if (!mesmaView) state.limiteGrade = LIMITE_GRADE;
    preencherGrid(grid, itens, { aoMais: () => abrirCategoria(cat) });
  }

  function renderFavoritos() {
    const grid = $("#grid-favoritos");
    const vazio = $("#empty-favoritos");
    const itens = catalog.todos().filter((c) => state.favoritos.has(String(c.id)));
    preencherGrid(grid, itens, { aoMais: renderFavoritos });
    vazio.classList.toggle("hidden", itens.length > 0);
  }

  function renderContinuar() {
    const grid = $("#grid-continuar");
    const vazio = $("#empty-continuar");
    const lista = store.getContinueWatching();
    const itens = lista
      .map((p) => {
        const item = catalog.porId(p.id);
        return item ? { ...item, progresso: p.progresso, posicao: p.atual } : null;
      })
      .filter(Boolean);

    grid.innerHTML = "";
    itens.forEach((item) => {
      grid.appendChild(criarCard(item, { progresso: item.progresso }));
    });
    vazio.classList.toggle("hidden", itens.length > 0);
  }

  function renderRecentes() {
    const grid = $("#grid-recentes");
    const vazio = $("#empty-recentes");
    const lista = store.getRecents();
    const itens = lista
      .map((r) => catalog.porId(r.id))
      .filter(Boolean);
    preencherGrid(grid, itens, { aoMais: renderRecentes });
    vazio.classList.toggle("hidden", itens.length > 0);
  }

  function renderBusca(termo) {
    const grid = $("#grid-busca");
    const vazio = $("#empty-busca");
    const titulo = $("#titulo-busca");
    const q = termo.trim();
    if (!q) {
      grid.innerHTML = "";
      vazio.classList.remove("hidden");
      titulo.textContent = "Resultados";
      return;
    }
    const itens = catalog.filtrar({ termo: q, incluirAdulto: state.settings.adulto });
    titulo.textContent = `Resultados para “${q}” (${itens.length})`;
    preencherGrid(grid, itens, { aoMais: () => renderBusca(termo) });
    vazio.classList.toggle("hidden", itens.length > 0);
  }

  /* ------------------------------------------------------------------
     Busca com debounce (250ms, igual ao Android)
  ------------------------------------------------------------------ */
  function configurarBusca() {
    const input = $("#busca");
    const limpar = $("#btn-limpar-busca");

    input.addEventListener("input", () => {
      const valor = input.value;
      limpar.classList.toggle("hidden", !valor);
      clearTimeout(state.buscaTimer);
      state.buscaTimer = setTimeout(() => {
        state.termo = valor;
        state.limiteGrade = LIMITE_GRADE;
        if (valor.trim()) navegar("busca");
        else navegar("ao-vivo");
      }, 250);
    });

    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        clearTimeout(state.buscaTimer);
        state.termo = input.value;
        state.limiteGrade = LIMITE_GRADE;
        navegar(state.termo.trim() ? "busca" : "ao-vivo");
      }
    });

    limpar.addEventListener("click", () => {
      input.value = "";
      state.termo = "";
      state.limiteGrade = LIMITE_GRADE;
      limpar.classList.add("hidden");
      navegar("ao-vivo");
    });
  }

  /* ------------------------------------------------------------------
     Série — temporadas e episódios
  ------------------------------------------------------------------ */
  function abrirSerie(serie) {
    const modal = $("#serie-modal");
    if (!modal) return;

    $("#serie-titulo").textContent = serie.nome;
    const totalTemporadas = serie.temporadas || new Set(serie.episodios.map((e) => e.temporada)).size;
    $("#serie-meta").textContent =
      `${totalTemporadas} ${totalTemporadas === 1 ? "temporada" : "temporadas"} · ` +
      `${serie.episodios.length} ${serie.episodios.length === 1 ? "episódio" : "episódios"}`;

    const poster = $("#serie-poster");
    poster.innerHTML = serie.logo
      ? `<img src="${escapeHtml(serie.logo)}" alt="" loading="lazy">`
      : `<span>${escapeHtml((serie.nome || "?").charAt(0).toUpperCase())}</span>`;

    const container = $("#serie-temporadas");
    container.innerHTML = "";

    const porTemporada = new Map();
    serie.episodios.forEach((ep) => {
      const t = Number(ep.temporada) || 1;
      if (!porTemporada.has(t)) porTemporada.set(t, []);
      porTemporada.get(t).push(ep);
    });

    [...porTemporada.keys()].sort((a, b) => a - b).forEach((temporada, indice) => {
      const detalhes = document.createElement("details");
      detalhes.className = "serie-temporada";
      detalhes.open = indice === 0;

      const resumo = document.createElement("summary");
      resumo.textContent = `Temporada ${temporada}`;
      detalhes.appendChild(resumo);

      const lista = document.createElement("div");
      lista.className = "serie-episodios";
      porTemporada.get(temporada)
        .sort((a, b) => a.episodio - b.episodio)
        .forEach((ep) => {
          const botao = document.createElement("button");
          botao.type = "button";
          botao.className = "serie-episodio";
          const titulo = ep.episodioTitulo || `Episódio ${ep.episodio}`;
          botao.innerHTML = `
            <span class="ep-num">T${ep.temporada} E${ep.episodio}</span>
            <span class="ep-nome">${escapeHtml(titulo)}</span>
          `;
          botao.addEventListener("click", () => {
            fecharSerie();
            abrirPlayer(ep);
          });
          lista.appendChild(botao);
        });

      detalhes.appendChild(lista);
      container.appendChild(detalhes);
    });

    if (typeof modal.showModal === "function") modal.showModal();
    else modal.hidden = false;
  }

  function fecharSerie() {
    const modal = $("#serie-modal");
    if (!modal) return;
    if (typeof modal.close === "function") modal.close();
    else modal.hidden = true;
  }

  function configurarSerie() {
    $("#serie-close").addEventListener("click", fecharSerie);
    const modal = $("#serie-modal");
    modal.addEventListener("click", (e) => {
      if (e.target === modal) fecharSerie();
    });
  }

  /* ------------------------------------------------------------------
     Player
  ------------------------------------------------------------------ */
  async function abrirPlayer(item) {
    if (item.tipo === "serie" && Array.isArray(item.episodios) && item.episodios.length) {
      abrirSerie(item);
      return;
    }
    if (!state.usuario && !state.demo) {
      abrirAuth("login");
      mostrarToast("Entre para assistir");
      return;
    }

    state.playerItem = item;
    store.addRecent({ id: item.id, nome: item.nome, grupo: item.grupo, tipo: item.tipo, aoVivo: item.aoVivo });

    // UI do player
    $("#player-wrap").classList.remove("hidden");
    $("#player-titulo").textContent = item.nome;
    $("#btn-favorito-player").textContent = state.favoritos.has(String(item.id)) ? "★" : "☆";
    $("#player-error").classList.add("hidden");
    $("#stream-limit").classList.add("hidden");
    $("#player-controls").classList.remove("hidden");
    $("#player-status").textContent = "Carregando…";
    $("#btn-ao-vivo").classList.toggle("hidden", !item.aoVivo);
    $("#time-current").textContent = "0:00";
    $("#time-duration").textContent = "0:00";
    $("#progress-filled").style.width = "0%";
    $("#progress-handle").style.left = "0%";

    player.init($("#video"));
    player.stop();

    // Tenta iniciar sessão no backend
    let streamUrl = item.url;
    let token = null;
    let sessionId = null;

    if (!state.demo && item.url) {
      try {
        const dados = await api.iniciarPlayer(item.url, item.nome);
        sessionId = dados.session_id || dados.sessionId || null;
      } catch (erro) {
        if (erro.status === 403 || (erro.corpo && erro.corpo.detail === "stream_limit")) {
          $("#stream-limit").classList.remove("hidden");
          return;
        }
        // Não troca o catálogo inteiro para demo por causa de uma falha
        // isolada ao registrar a sessão do player.
        mostrarToast("Não foi possível registrar a sessão; tentando reproduzir direto.");
      }
    }

    // Sem URL real (demo): usa o vídeo de demonstração local.
    if (!streamUrl) {
      streamUrl = "assets/media/demo.mp4";
    }

    state.playerSessao = sessionId;
    if (sessionId) player.iniciarSessao(sessionId);

    const tipo = item.streamType || (item.url ? tipoStream(item) : "mp4");

    try {
      await player.carregar(item, { url: streamUrl, tipo, token });

      // Retoma progresso salvo (filmes/séries)
      if (item.tipo !== "canal" && !item.aoVivo) {
        const prog = store.getProgress()[String(item.id)];
        if (prog && prog.atual > 5) {
          const tentarRetomar = () => {
            try { player.seek(prog.atual); } catch (_) {}
            player.video.removeEventListener("loadedmetadata", tentarRetomar);
          };
          player.video.addEventListener("loadedmetadata", tentarRetomar);
        }
      }

      if (state.settings.autoplay) {
        player.play().catch(() => {
          $("#btn-play-pause").textContent = "▶";
        });
      }
    } catch (erro) {
      $("#player-error").classList.remove("hidden");
      $("#player-error-text").textContent = erro.message || "Não foi possível iniciar a transmissão.";
    }

    atualizarBotoesPlayer();
  }

  function fecharPlayer() {
    const id = state.playerItem ? state.playerItem.id : null;
    const atual = player.getCurrentTime();
    const dur = player.getDuration();
    if (id && dur > 0 && atual > 5) {
      const progresso = Math.min(100, (atual / dur) * 100);
      store.saveProgress(id, { atual, duracao: dur, progresso });
    }

    player.encerrarSessao();
    player.stop();
    state.playerSessao = null;
    state.playerItem = null;
    $("#player-wrap").classList.add("hidden");
    $("#menu-qualidade").classList.add("hidden");
    $("#menu-audio").classList.add("hidden");
    $("#menu-legenda").classList.add("hidden");
    $("#player-error").classList.add("hidden");
    $("#stream-limit").classList.add("hidden");
  }

  function atualizarBotoesPlayer() {
    const v = player.video;
    if (!v) return;
    $("#btn-play-pause").textContent = v.paused ? "▶" : "⏸";
    $("#btn-mudo").textContent = v.muted ? "🔇" : "🔊";
  }

  function configurarPlayerUI() {
    const video = $("#video");

    player.subscribe((evento, dado) => {
      switch (evento) {
        case "ready":
        case "loadeddata":
          $("#player-status").textContent = "Pronto";
          break;
        case "playing":
          $("#player-status").textContent = state.playerItem?.aoVivo ? "Ao vivo" : "Reproduzindo";
          $("#btn-play-pause").textContent = "⏸";
          $("#player-error").classList.add("hidden");
          break;
        case "pause":
          $("#btn-play-pause").textContent = "▶";
          break;
        case "waiting":
          $("#player-status").textContent = "Carregando…";
          break;
        case "reconectando":
          $("#player-status").textContent = `Reconectando… (${dado?.tentativa || 1})`;
          break;
        case "progress":
          if (dado && dado.item && dado.item.tipo !== "canal") {
            store.saveProgress(dado.item.id, {
              atual: dado.atual,
              duracao: dado.duracao,
              progresso: dado.progresso,
            });
            const pct = dado.progresso;
            $("#progress-filled").style.width = pct + "%";
            $("#progress-handle").style.left = pct + "%";
            $("#time-current").textContent = fmtTempo(dado.atual);
            $("#time-duration").textContent = fmtTempo(dado.duracao);
          }
          break;
        case "error":
          $("#player-error").classList.remove("hidden");
          $("#player-error-text").textContent = (dado && dado.message) || "Não foi possível iniciar a transmissão.";
          break;
        case "sessao-encerrada":
          $("#stream-limit").classList.remove("hidden");
          break;
      }
    });

    // Barra de progresso
    video.addEventListener("timeupdate", () => {
      if (!Number.isFinite(video.duration) || video.duration <= 0) return;
      const pct = (video.currentTime / video.duration) * 100;
      $("#progress-filled").style.width = pct + "%";
      $("#progress-handle").style.left = pct + "%";
      $("#time-current").textContent = fmtTempo(video.currentTime);
      $("#time-duration").textContent = fmtTempo(video.duration);
    });

    $("#progress-bar").addEventListener("click", (e) => {
      if (!Number.isFinite(video.duration) || video.duration <= 0) return;
      const rect = e.currentTarget.getBoundingClientRect();
      const pct = Math.min(1, Math.max(0, (e.clientX - rect.left) / rect.width));
      player.seek(pct * video.duration);
    });

    $("#btn-play-pause").addEventListener("click", () => {
      player.toggle();
      setTimeout(atualizarBotoesPlayer, 50);
    });
    $("#btn-voltar-10").addEventListener("click", () => player.seekRelativo(-10));
    $("#btn-avancar-10").addEventListener("click", () => player.seekRelativo(10));
    $("#btn-mudo").addEventListener("click", () => {
      player.toggleMute();
      atualizarBotoesPlayer();
    });
    $("#btn-fullscreen").addEventListener("click", () => player.toggleFullscreen());
    $("#btn-pip").addEventListener("click", async () => {
      const ok = await player.togglePiP();
      if (!ok) mostrarToast("Picture-in-Picture não suportado neste navegador");
    });
    $("#btn-ao-vivo").addEventListener("click", () => player.irParaAoVivo());
    $("#btn-fechar-player").addEventListener("click", fecharPlayer);
    $("#btn-retry-player").addEventListener("click", () => {
      if (state.playerItem) abrirPlayer(state.playerItem);
    });
    $("#btn-fechar-limite").addEventListener("click", () => {
      $("#stream-limit").classList.add("hidden");
      fecharPlayer();
    });
    $("#btn-favorito-player").addEventListener("click", () => {
      if (!state.playerItem) return;
      toggleFavorito(state.playerItem.id);
      $("#btn-favorito-player").textContent = state.favoritos.has(String(state.playerItem.id)) ? "★" : "☆";
    });

    // Menus de faixas
    $("#btn-qualidade").addEventListener("click", (e) => {
      e.stopPropagation();
      abrirMenuFaixas("qualidade");
    });
    $("#btn-audio").addEventListener("click", (e) => {
      e.stopPropagation();
      abrirMenuFaixas("audio");
    });
    $("#btn-legenda").addEventListener("click", (e) => {
      e.stopPropagation();
      abrirMenuFaixas("legenda");
    });

    document.addEventListener("click", (e) => {
      if (!e.target.closest(".track-menu") && !e.target.closest(".ctrl-btn")) {
        ["qualidade", "audio", "legenda"].forEach((t) => $("#menu-" + t).classList.add("hidden"));
      }
    });

    // Mostrar/esconder controles
    const wrap = $("#player-wrap");
    wrap.addEventListener("mousemove", () => {
      $("#player-controls").classList.remove("hidden");
      clearTimeout(wrap._timer);
      wrap._timer = setTimeout(() => {
        if (player.isPlaying()) $("#player-controls").classList.add("hidden");
      }, 3200);
    });

    // Teclado (TV / desktop)
    document.addEventListener("keydown", (e) => {
      if ($("#player-wrap").classList.contains("hidden")) return;
      if (e.key === "Escape") fecharPlayer();
      if (e.key === " " || e.key === "k") { e.preventDefault(); player.toggle(); }
      if (e.key === "ArrowLeft") player.seekRelativo(-10);
      if (e.key === "ArrowRight") player.seekRelativo(10);
      if (e.key === "f") player.toggleFullscreen();
      if (e.key === "m") { player.toggleMute(); atualizarBotoesPlayer(); }
    });
  }

  function abrirMenuFaixas(tipo) {
    const menu = $("#menu-" + tipo);
    const faixas = player.faixas();
    const lista = faixas[tipo] || [];

    if (!lista.length) {
      mostrarToast("Nenhuma faixa disponível para este stream");
      return;
    }

    menu.innerHTML = "";
    lista.forEach((f) => {
      const b = document.createElement("button");
      b.className = "track-item" + (f.ativo ? " active" : "");
      b.textContent = f.rotulo;
      b.addEventListener("click", () => {
        if (tipo === "qualidade") player.selecionarQualidade(f.id);
        if (tipo === "audio") player.selecionarAudio(f.id);
        if (tipo === "legenda") player.selecionarLegenda(f.id);
        menu.classList.add("hidden");
      });
      menu.appendChild(b);
    });
    menu.classList.remove("hidden");
  }

  /* ------------------------------------------------------------------
     Conta / Assinatura
  ------------------------------------------------------------------ */
  async function carregarConta() {
    const card = $("#account-card");
    const acoes = $("#account-actions");
    card.innerHTML = '<div class="account-loading">Carregando assinatura…</div>';
    acoes.hidden = true;

    if (!state.usuario) {
      card.innerHTML = `
        <div class="account-empty">
          <div class="empty-icon">🔒</div>
          <h3>Entre para ver sua assinatura</h3>
          <p>Acesse planos, pagamentos e dispositivos.</p>
          <button class="btn btn-primary btn-block" id="btn-login-conta">Entrar ou criar conta</button>
        </div>
      `;
      $("#btn-login-conta").addEventListener("click", () => abrirAuth("login"));
      return;
    }

    let assinatura = null;
    let planos = [];

    if (!state.demo) {
      try {
        const [a, p] = await Promise.allSettled([api.assinatura(), api.planos()]);
        if (a.status === "fulfilled") assinatura = a.value;
        if (p.status === "fulfilled") {
          planos = Array.isArray(p.value) ? p.value : (p.value && (p.value.plans || p.value.planos)) || [];
        }
      } catch (_) {}
    }

    state.planos = planos;
    state.planoPadrao =
      planos.find((p) => p.active !== false && (p.periodicidade === "mensal" || p.interval === "month" || !p.interval)) ||
      planos[0] ||
      null;

    if (!assinatura) {
      assinatura = {
        status: "trialing",
        plano: state.planoPadrao
          ? `${state.planoPadrao.name || state.planoPadrao.nome || "Mensal"} — ${formatarPreco(state.planoPadrao)}`
          : "Mensal — R$ 19,90/mês",
        plano_id: state.planoPadrao ? state.planoPadrao.id : null,
        dias_restantes: 7,
        valido_ate: new Date(Date.now() + 7 * 86400000).toLocaleDateString("pt-BR"),
        pagamento: "Demonstração",
      };
    }

    // Normaliza nomes de campos do backend (snake_case / camelCase / aninhados).
    assinatura = {
      ...assinatura,
      status: String(assinatura.status || "unknown").toLowerCase(),
      plano:
        assinatura.plano ||
        assinatura.plan_name ||
        (assinatura.plan && (assinatura.plan.name || assinatura.plan.nome)) ||
        "—",
      plano_id:
        assinatura.plano_id ||
        assinatura.plan_id ||
        (assinatura.plan && assinatura.plan.id) ||
        (state.planoPadrao && state.planoPadrao.id) ||
        null,
      valido_ate:
        assinatura.valido_ate ||
        assinatura.current_period_end ||
        assinatura.expires_at ||
        "—",
      dias_restantes:
        assinatura.dias_restantes != null ? assinatura.dias_restantes : assinatura.days_left,
      pagamento:
        assinatura.pagamento ||
        (assinatura.payment_method
          ? assinatura.payment_method + (assinatura.payment_last_four ? " •••• " + assinatura.payment_last_four : "")
          : assinatura.provider) ||
        "—",
      subscription_id: assinatura.subscription_id || assinatura.id || null,
      max_dispositivos: assinatura.max_devices,
      max_telas: assinatura.max_streams,
    };
    if (typeof assinatura.valido_ate === "string" && /^\d{4}-\d{2}-\d{2}/.test(assinatura.valido_ate)) {
      try {
        assinatura.valido_ate = new Date(assinatura.valido_ate).toLocaleDateString("pt-BR");
      } catch (_) {}
    }
    state.assinatura = assinatura;

    const statusLabel = {
      active: "● Ativo",
      trial: "● Teste grátis",
      trialing: "● Teste grátis",
      pending: "● Aguardando pagamento",
      past_due: "● Pagamento pendente",
      cancelled: "● Cancelado",
      canceled: "● Cancelado",
      expired: "● Expirado",
      none: "● Sem assinatura",
    }[assinatura.status] || "● " + assinatura.status;

    card.innerHTML = `
      <div class="conta-linha"><span>E-mail</span><strong>${escapeHtml(state.usuario.email)}</strong></div>
      <div class="conta-linha"><span>Plano</span><strong>${escapeHtml(assinatura.plano || "—")}</strong></div>
      <div class="conta-linha"><span>Status</span><strong class="status-${assinatura.status}">${statusLabel}</strong></div>
      <div class="conta-linha"><span>Válido até</span><strong>${escapeHtml(assinatura.valido_ate || "—")}</strong></div>
      <div class="conta-linha"><span>Pagamento</span><strong>${escapeHtml(assinatura.pagamento || "—")}</strong></div>
      ${assinatura.dias_restantes != null ? `<div class="conta-linha"><span>Dias restantes</span><strong>${assinatura.dias_restantes}</strong></div>` : ""}
    `;

    acoes.hidden = false;
    $("#btn-cancelar").hidden = !["active", "trial", "trialing"].includes(assinatura.status);
  }

  function configurarConta() {
    $("#btn-assinar").addEventListener("click", async () => {
      if (!state.usuario) { abrirAuth("login"); return; }
      if (state.demo) {
        mostrarToast("Modo demonstração: checkout simulado");
        return;
      }
      try {
        const planoId = state.assinatura?.plano_id || (state.planoPadrao && state.planoPadrao.id) || 1;
        const dados = await api.checkout(planoId);
        const destino = dados.init_point || dados.checkout_url || dados.url || dados.sandbox_init_point;
        if (destino) {
          window.location.href = destino;
        } else {
          mostrarToast("Checkout indisponível no momento");
        }
      } catch (erro) {
        mostrarToast("Não foi possível abrir o checkout: " + erro.message);
      }
    });

    $("#btn-cancelar").addEventListener("click", async () => {
      if (!confirm("Cancelar a assinatura? O acesso continua até o fim do período pago.")) return;
      try {
        if (!state.assinatura || !state.assinatura.subscription_id) {
          mostrarToast("Assinatura não encontrada");
          return;
        }
        await api.cancelar(state.assinatura.subscription_id);
        mostrarToast("Assinatura cancelada");
        carregarConta();
      } catch (erro) {
        mostrarToast("Erro ao cancelar: " + erro.message);
      }
    });

    $("#btn-restaurar").addEventListener("click", async () => {
      mostrarToast("Verificando assinatura…");
      if (!state.demo) {
        try { await api.sincronizarAssinatura(); } catch (_) {}
      }
      carregarConta();
    });

    $("#btn-dispositivos").addEventListener("click", async () => {
      const card = $("#devices-card");
      card.classList.toggle("hidden");
      if (card.classList.contains("hidden")) return;
      const lista = $("#lista-dispositivos");
      lista.innerHTML = '<p class="muted">Carregando dispositivos…</p>';
      if (state.demo) {
        lista.innerHTML = "<p>Web PWA (este aparelho) — ativo</p>";
        return;
      }
      try {
        const dados = await api.dispositivo();
        const itens = dados.devices || dados.aparelhos || [];
        lista.innerHTML = itens.length
          ? itens.map((d) => {
              const nome = d.device_name || d.name || d.nome || "Aparelho";
              const atual = d.current ? " (este aparelho)" : "";
              const visto = d.last_seen_at ? " — visto " + new Date(d.last_seen_at).toLocaleDateString("pt-BR") : "";
              return `<p>${escapeHtml(nome)}${atual}${visto}</p>`;
            }).join("")
          : "<p>Nenhum dispositivo vinculado.</p>";
      } catch (erro) {
        lista.innerHTML = `<p class="muted">Não foi possível carregar: ${escapeHtml(erro.message)}</p>`;
      }
    });

    $("#btn-revogar-dispositivos").addEventListener("click", async () => {
      if (!confirm("Desvincular todos os aparelhos? Você precisará entrar de novo em cada um.")) return;
      try {
        await api.revogarDispositivos();
        mostrarToast("Dispositivos desvinculados");
        $("#lista-dispositivos").innerHTML = "<p>Nenhum dispositivo vinculado.</p>";
      } catch (erro) {
        mostrarToast("Erro: " + erro.message);
      }
    });
  }

  /* ------------------------------------------------------------------
     Auth
  ------------------------------------------------------------------ */
  function abrirAuth(aba = "login") {
    const modal = $("#auth-modal");
    trocarAbaAuth(aba);
    if (typeof modal.showModal === "function") modal.showModal();
    else modal.hidden = false;
  }

  function fecharAuth() {
    const modal = $("#auth-modal");
    if (typeof modal.close === "function") modal.close();
    else modal.hidden = true;
  }

  function trocarAbaAuth(aba) {
    $$(".auth-tab").forEach((t) => t.classList.toggle("active", t.dataset.authTab === aba));
    $("#form-login").classList.toggle("hidden", aba !== "login");
    $("#form-register").classList.toggle("hidden", aba !== "register");
    $("#form-forgot").classList.toggle("hidden", aba !== "forgot");
  }

  function sessaoLocal(email) {
    return {
      access: "demo-access",
      refresh: "demo-refresh",
      email,
    };
  }

  function configurarAuth() {
    $("#auth-close").addEventListener("click", fecharAuth);
    $$(".auth-tab").forEach((t) => {
      t.addEventListener("click", () => trocarAbaAuth(t.dataset.authTab));
    });

    $("#form-login").addEventListener("submit", async (e) => {
      e.preventDefault();
      const fd = new FormData(e.currentTarget);
      const email = String(fd.get("email") || "").trim();
      const senha = String(fd.get("senha") || "");
      if (!email || !senha) return;

      try {
        const dados = await api.login(email, senha);
        state.usuario = { email, ...dados };
        state.demo = false;
        // api.login já salvou a sessão real (access + refresh).
        await iniciarPosLogin();
        fecharAuth();
        mostrarToast("Bem-vindo de volta!");
      } catch (erro) {
        const falhaDeRede = !erro.status || erro.status >= 500;
        if (cfg.DEMO_FALLBACK && falhaDeRede) {
          state.usuario = { email };
          state.demo = true;
          store.setSession(sessaoLocal(email));
          await iniciarPosLogin();
          fecharAuth();
          mostrarToast("Backend offline — modo demonstração ativado");
        } else if (erro.status === 401) {
          mostrarToast("E-mail ou senha inválidos");
        } else {
          mostrarToast(erro.message || "Falha no login");
        }
      }
    });

    $("#form-register").addEventListener("submit", async (e) => {
      e.preventDefault();
      const fd = new FormData(e.currentTarget);
      const nome = String(fd.get("nome") || "").trim();
      const email = String(fd.get("email") || "").trim();
      const senha = String(fd.get("senha") || "");
      try {
        await api.registrar(nome, email, senha);
        mostrarToast("Conta criada! Confirme o e-mail para ativar o teste.");
        trocarAbaAuth("login");
      } catch (erro) {
        const falhaDeRede = !erro.status || erro.status >= 500;
        if (cfg.DEMO_FALLBACK && falhaDeRede) {
          state.usuario = { email };
          state.demo = true;
          store.setSession(sessaoLocal(email));
          await iniciarPosLogin();
          fecharAuth();
          mostrarToast("Backend offline — conta de demonstração criada");
        } else {
          mostrarToast(erro.message || "Falha no cadastro");
        }
      }
    });

    // Esqueci a senha
    $("#link-esqueci").addEventListener("click", (e) => {
      e.preventDefault();
      trocarAbaAuth("forgot");
    });
    $("#link-voltar-login").addEventListener("click", (e) => {
      e.preventDefault();
      trocarAbaAuth("login");
    });

    let codigoEnviado = false;
    $("#form-forgot").addEventListener("submit", async (e) => {
      e.preventDefault();
      const fd = new FormData(e.currentTarget);
      const email = String(fd.get("email") || "").trim();
      if (!codigoEnviado) {
        try {
          await api.esqueciSenha(email);
          codigoEnviado = true;
          $("#campo-codigo").classList.remove("hidden");
          $("#campo-nova-senha").classList.remove("hidden");
          $("#btn-redefinir").classList.remove("hidden");
          mostrarToast("Código enviado para o e-mail");
        } catch (erro) {
          mostrarToast("Erro: " + erro.message);
        }
        return;
      }
      const codigo = String(fd.get("codigo") || "");
      const novaSenha = String(fd.get("novaSenha") || "");
      try {
        await api.redefinirSenha(email, codigo, novaSenha);
        mostrarToast("Senha redefinida! Faça login.");
        codigoEnviado = false;
        trocarAbaAuth("login");
      } catch (erro) {
        mostrarToast("Erro: " + erro.message);
      }
    });
  }

  async function iniciarPosLogin() {
    $("#sidebar-user").textContent = state.usuario.email.split("@")[0];
    // Recarrega o catálogo real (playlist autenticada).
    state.demo = false;
    await carregarCatalogo(true);
    renderAoVivo();
    if (state.view === "conta") carregarConta();
  }

  async function sair() {
    await api.logout();
    store.clearSession();
    await store.clearCatalogCacheAsync();
    catalog.usarDemo();
    state.usuario = null;
    state.assinatura = null;
    state.demo = true;
    state.catalogError = null;
    $("#sidebar-user").textContent = "Convidado";
    mostrarToast("Você saiu da conta");
    navegar("ao-vivo");
  }

  /* ------------------------------------------------------------------
     Ajustes
  ------------------------------------------------------------------ */
  function renderAjustes() {
    $("#set-adulto").checked = !!state.settings.adulto;
    $("#set-tv").checked = !!state.settings.modoTV;
    $("#set-economia").checked = !!state.settings.economizarDados;
    $("#set-autoplay").checked = !!state.settings.autoplay;
    document.body.classList.toggle("modo-tv", !!state.settings.modoTV);
    const fonte = catalog.fonte || (state.demo ? "demo" : "—");
    const erro = state.catalogError ? ` · Erro: ${state.catalogError}` : "";
    $("#settings-api").textContent =
      `API: ${cfg.API_URL} · Versão: ${cfg.APP_VERSION} · Catálogo: ${fonte} (${catalog.canais.length} itens)${erro}`;
  }

  function configurarAjustes() {
    $("#set-adulto").addEventListener("change", (e) => {
      state.settings.adulto = e.target.checked;
      store.saveSettings({ adulto: e.target.checked });
      mostrarToast(e.target.checked ? "Conteúdo adulto liberado" : "Conteúdo adulto oculto");
      if (state.view === "ao-vivo") renderAoVivo();
    });
    $("#set-tv").addEventListener("change", (e) => {
      state.settings.modoTV = e.target.checked;
      store.saveSettings({ modoTV: e.target.checked });
      document.body.classList.toggle("modo-tv", e.target.checked);
    });
    $("#set-economia").addEventListener("change", (e) => {
      state.settings.economizarDados = e.target.checked;
      store.saveSettings({ economizarDados: e.target.checked });
    });
    $("#set-autoplay").addEventListener("change", (e) => {
      state.settings.autoplay = e.target.checked;
      store.saveSettings({ autoplay: e.target.checked });
    });

    $("#btn-limpar-cache").addEventListener("click", async () => {
      await store.clearCatalogCacheAsync();
      mostrarToast("Cache limpo. Recarregando catálogo…");
      await carregarCatalogo(true);
      renderAoVivo();
    });

    $("#btn-instalar-ajustes").addEventListener("click", () => {
      const dialog = $("#install-dialog");
      if (typeof dialog.showModal === "function") dialog.showModal();
      else dialog.hidden = false;
    });

    $("#btn-tv-code").addEventListener("click", abrirCodigoTV);
  }

  function renderAjuda() {
    $("#demo-note").hidden = !state.demo;
  }

  /* ------------------------------------------------------------------
     TV code
  ------------------------------------------------------------------ */
  async function abrirCodigoTV() {
    const modal = $("#tv-modal");
    if (typeof modal.showModal === "function") modal.showModal();
    else modal.hidden = false;
    $("#tv-status").textContent = "";
  }

  function configurarTV() {
    $("#tv-close").addEventListener("click", () => {
      const m = $("#tv-modal");
      if (typeof m.close === "function") m.close();
      else m.hidden = true;
    });

    $("#btn-gerar-codigo").addEventListener("click", async () => {
      const el = $("#tv-code");
      el.textContent = "······";
      $("#tv-status").textContent = "Gerando…";
      try {
        const dados = await api.gerarCodigoTV();
        el.textContent = dados.code || dados.codigo || "------";
        $("#tv-status").textContent = "Aguardando autorização no celular…";
        // Poll
        const codigo = dados.code || dados.codigo;
        const intervalo = setInterval(async () => {
          try {
            const r = await api.consultarCodigoTV(codigo);
            if (r && (r.access_token || r.status === "approved")) {
              clearInterval(intervalo);
              $("#tv-status").textContent = "Autorizado!";
              if (r.access_token) {
                store.setSession({ access: r.access_token, refresh: r.refresh_token, email: r.email || "tv@eftv" });
                state.usuario = { email: r.email || "tv@eftv" };
                state.demo = false;
                await iniciarPosLogin();
                const m = $("#tv-modal");
                if (typeof m.close === "function") m.close();
              }
            }
          } catch (_) {}
        }, 3000);
        setTimeout(() => clearInterval(intervalo), 5 * 60 * 1000);
      } catch (_) {
        el.textContent = "------";
        $("#tv-status").textContent = "Modo demonstração: use o app Android para autorizar.";
      }
    });
  }

  /* ------------------------------------------------------------------
     Catálogo
  ------------------------------------------------------------------ */
  async function carregarCatalogo(forcar = false) {
    if (state.carregando) return;
    state.carregando = true;
    const loading = $("#catalog-loading");
    if (loading) loading.classList.remove("hidden");

    if (!store.getSession() || state.demo || (store.getSession() && store.getSession().access === "demo-access")) {
      catalog.usarDemo();
      state.demo = true;
      state.catalogError = null;
    } else {
      try {
        await catalog.carregar(forcar);
        state.demo = catalog.demo;
        state.catalogError = null;
        if (catalog.erro) {
          mostrarToast("Não foi possível atualizar; usando o catálogo salvo.");
        }
      } catch (erro) {
        state.demo = false;
        state.catalogError = erro.message || "Falha ao carregar o catálogo";
        if (cfg.DEMO_FALLBACK) {
          catalog.usarDemo();
          state.demo = true;
        } else if (!catalog.canais.length || catalog.demo) {
          catalog.limpar();
        }
        mostrarToast(state.catalogError);
      }
    }

    state.carregando = false;
    if (loading) loading.classList.add("hidden");
    const badge = $("#demo-note");
    if (badge) badge.hidden = !state.demo;
    if (state.view === "ajustes") renderAjustes();
  }

  /* ------------------------------------------------------------------
     Erros
  ------------------------------------------------------------------ */
  function configurarErros() {
    window.addEventListener("error", (e) => {
      api.reportarErro({
        message: e.message,
        source: e.filename,
        line: e.lineno,
        column: e.colno,
        stack: e.error ? String(e.error.stack) : null,
        version: cfg.APP_VERSION,
        device: store.deviceId(),
        platform: "web",
      });
    });
    window.addEventListener("unhandledrejection", (e) => {
      api.reportarErro({
        message: String(e.reason && (e.reason.message || e.reason)),
        stack: e.reason && e.reason.stack ? String(e.reason.stack) : null,
        version: cfg.APP_VERSION,
        device: store.deviceId(),
        platform: "web",
      });
    });
  }

  /* ------------------------------------------------------------------
     Sidebar
  ------------------------------------------------------------------ */
  function abrirSidebar() {
    $("#sidebar").classList.add("open");
    $("#overlay").classList.add("visible");
  }
  function fecharSidebar() {
    $("#sidebar").classList.remove("open");
    $("#overlay").classList.remove("visible");
  }

  function configurarSidebar() {
    $("#btn-menu").addEventListener("click", abrirSidebar);
    $("#overlay").addEventListener("click", fecharSidebar);
    $$(".nav-link").forEach((link) => {
      link.addEventListener("click", (e) => {
        e.preventDefault();
        navegar(link.dataset.view);
      });
    });
    $("#btn-logout").addEventListener("click", sair);
    $("#btn-perfil").addEventListener("click", () => {
      if (state.usuario) navegar("conta");
      else abrirAuth("login");
    });
  }

  /* ------------------------------------------------------------------
     Init
  ------------------------------------------------------------------ */
  async function init() {
    const params = new URLSearchParams(location.search);

    // Modo demonstração explícito (útil para testar a interface sem backend).
    if (params.get("demo") === "1" && cfg.DEMO_MODE && !store.getSession()) {
      store.setSession(sessaoLocal("cliente@eftv.com.br"));
    }

    // Sessão salva
    const sessao = store.getSession();
    if (sessao && sessao.email) {
      state.usuario = { email: sessao.email };
      $("#sidebar-user").textContent = sessao.email.split("@")[0];
      if (sessao.access === "demo-access") state.demo = true;
    }

    $("#app-version").textContent = `Web PWA · v${cfg.APP_VERSION}`;
    document.body.classList.toggle("modo-tv", !!state.settings.modoTV);

    configurarSidebar();
    configurarBusca();
    configurarPlayerUI();
    configurarConta();
    configurarAuth();
    configurarAjustes();
    configurarTV();
    configurarSerie();
    configurarErros();

    $("#btn-atualizar-catalogo").addEventListener("click", async () => {
      mostrarToast("Atualizando catálogo…");
      await carregarCatalogo(true);
      renderAoVivo();
      mostrarToast("Catálogo atualizado");
    });

    $("#btn-voltar-categoria").addEventListener("click", () => navegar("categorias"));

    window.addEventListener("hashchange", () => navegar(rotaDoHash(), { hash: false }));

    await carregarCatalogo(false);
    navegar(rotaDoHash(), { hash: false });

    // Deep link: ?canal=slug ou ?id=123 abre direto o conteúdo.
    const alvo = params.get("canal") || params.get("id");
    if (alvo) {
      const item = catalog.porSlug(alvo) || catalog.porId(alvo);
      if (item) abrirPlayer(item);
      else mostrarToast("Conteúdo não encontrado no catálogo");
    }

    // Confirmação de e-mail: ?verify=TOKEN
    const tokenVerificacao = params.get("verify");
    if (tokenVerificacao) {
      try {
        await api.verificarEmail(tokenVerificacao);
        mostrarToast("E-mail confirmado! Seu teste grátis de 7 dias está ativo.");
      } catch (erro) {
        mostrarToast(erro.message || "Não foi possível confirmar o e-mail");
      }
      params.delete("verify");
      const qs = params.toString();
      try {
        history.replaceState(null, "", location.pathname + (qs ? "?" + qs : "") + location.hash);
      } catch (_) {}
    }
  }

  init();
})();