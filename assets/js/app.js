/* EFTV - camada compartilhada: busca, filtros, categorias e helpers.
   A grade é montada sobre o catálogo local (playlists importadas), com
   renderização limitada para não travar o navegador em listas grandes. */

(function () {
  const norm = window.canaisNormalize;
  const escapeHtml = window.canaisEscape;
  const fmt = new Intl.NumberFormat("pt-BR");
  const LIMITE_GRADE = 240;
  const LIMITE_AO_VIVO = 14;
  let limiteGrade = LIMITE_GRADE;
  let filtroAtual = { texto: "", categoria: "" };

  /* ------------------------------------------------------------ "API" local */
  const CanaisAPI = {
    async buscar(query, limite = 8) {
      const q = norm(query);
      if (q.length < 2) return [];
      const dados = window.CANAIS_DATA;
      return dados.canais
        .filter(
          (c) =>
            (!window.CANAIS_ADULTOS || !window.canaisEhAdulto(c)) &&
            (norm(c.nome).includes(q) ||
              norm(c.categoria).includes(q) ||
              norm(c.grupo || "").includes(q))
        )
        .slice(0, limite)
        .map((c) => ({ titulo: c.nome, link: `canal.html?c=${c.slug}`, categoria: c.categoria }));
    },

    porSlug(slug) {
      const dados = window.CANAIS_DATA;
      return dados.canais.find((c) => c.slug === slug);
    },

    categoriaNome(id) {
      const cat = window.CANAIS_DATA.categorias.find((c) => c.id === id);
      if (cat) return cat.nome;
      const meta = (window.CANAIS_CATEGORIAS || []).find((c) => c.id === id);
      return meta ? meta.nome : id;
    },
  };
  window.CanaisAPI = CanaisAPI;

  function metaCategoria(id) {
    return (
      (window.CANAIS_CATEGORIAS || []).find((c) => c.id === id) || {
        id,
        nome: id,
        icone: "•",
        cor: "#4fb5ff",
        descricao: "",
      }
    );
  }

  /* Lista filtrada sobre os dados (não sobre o DOM). Assim a busca e o filtro
     continuam funcionando mesmo quando a grade mostra só uma parte dos canais. */
  function canaisFiltrados() {
    const dados = window.CANAIS_DATA;
    const lista = (dados && dados.canais) || [];
    const q = norm(filtroAtual.texto || "");
    const cat = (filtroAtual.categoria || "").trim();

    let filtrados = lista;
    // Canais 18+ ficam fora da grade enquanto o usuario nao os liberar.
    if (!window.CANAIS_ADULTOS) {
      filtrados = filtrados.filter((c) => !window.canaisEhAdulto(c));
    }
    if (q) {
      filtrados = filtrados.filter((c) => {
        const nome = norm(c.nome || "");
        const grupo = norm(c.grupo || "");
        const categoria = norm(CanaisAPI.categoriaNome(c.categoria || ""));
        return nome.includes(q) || grupo.includes(q) || categoria.includes(q);
      });
    }

    if (!cat) return filtrados;
    if (cat === "__ao_vivo") return filtrados.filter((c) => c.aoVivo !== false);
    if (cat === "__sob_demanda") return filtrados.filter((c) => c.aoVivo === false);
    const categoria = norm(cat);
    return filtrados.filter((c) => norm(c.categoria || "") === categoria);
  }

  /* ------------------------------------------------------------- card HTML */
  function grupoCurto(grupo) {
    return String(grupo || "")
      .replace(/^(canais?|filmes?|s[eé]ries?)\s*\|\s*/i, "")
      .replace(/\[[^\]]*\]/g, " ")
      .replace(/\s+/g, " ")
      .trim();
  }

  function cardHTML(c) {
    const categoriaBase = CanaisAPI.categoriaNome(c.categoria);
    const curto = grupoCurto(c.grupo);
    const categoria =
      curto && norm(curto).replace(/s$/, "") !== norm(categoriaBase).replace(/s$/, "")
        ? `${categoriaBase} · ${curto}`
        : categoriaBase;
    const logo = c.logo
      ? `<img src="${escapeHtml(c.logo)}" alt="${escapeHtml(c.nome)}" loading="lazy" data-thumb>`
      : "";
    const aoVivo = c.aoVivo !== false;
    return `
      <a class="channel-card" href="canal.html?c=${encodeURIComponent(c.slug)}"
         data-channel-card data-name="${escapeHtml(c.nome)}"
         data-category="${escapeHtml(c.categoria)}"
         data-group="${escapeHtml(c.grupo || "")}">
        <div class="thumb">
          <span class="thumb-fallback" aria-hidden="true">${escapeHtml(window.canaisIniciais(c.nome))}</span>
          ${logo}
        </div>
        <span class="cat">${escapeHtml(categoria)}</span>
        <span class="name">${escapeHtml(c.nome)}</span>
        <span class="state${aoVivo ? "" : " vod"}"><i class="dot"></i> ${aoVivo ? "Ao vivo" : "Sob demanda"}</span>
      </a>`;
  }

  function ligarFallbackLogos(container) {
    container.querySelectorAll("img[data-thumb]").forEach((img) => {
      img.addEventListener("error", () => img.remove(), { once: true });
    });
  }

  /* ------------------------------------------------------------ categorias */
  function renderCategorias() {
    const secao = document.querySelector("[data-category-section]");
    const grade = document.querySelector("[data-category-grid]");
    const resumo = document.querySelector("[data-category-summary]");
    const filtros = document.getElementById("filtros");
    if (!secao || !grade || !filtros) return;

    const canais = (window.CANAIS_DATA && window.CANAIS_DATA.canais) || [];
    // Canais 18+ somem da grade, da busca e do resumo enquanto ocultos.
    const visiveis = window.CANAIS_ADULTOS
      ? canais
      : canais.filter((c) => !window.canaisEhAdulto(c));
    const total = visiveis.length;

    // Recria apenas os chips de categoria; os chips de status ficam fixos.
    filtros.querySelectorAll("[data-cat-chip]").forEach((el) => el.remove());

    if (!total) {
      secao.hidden = true;
      grade.innerHTML = "";
      if (resumo) resumo.textContent = "";
      atualizarChipsAtivos();
      return;
    }

    const contagem = new Map();
    const aoVivoPorCategoria = new Map();
    visiveis.forEach((c) => {
      const id = c.categoria || "outros";
      contagem.set(id, (contagem.get(id) || 0) + 1);
      if (c.aoVivo !== false) {
        aoVivoPorCategoria.set(id, (aoVivoPorCategoria.get(id) || 0) + 1);
      }
    });

    const metas = (window.CANAIS_CATEGORIAS || [])
      .filter((meta) => (contagem.get(meta.id) || 0) > 0)
      .filter((meta) => !(meta.id === "adultos" && !window.CANAIS_ADULTOS))
      .sort((a, b) => {
        const ordem = window.CANAIS_CATEGORIAS.map((x) => x.id);
        return ordem.indexOf(a.id) - ordem.indexOf(b.id);
      });

    // Se a categoria ativa sumiu (playlist removida), volta para "Todas".
    if (
      filtroAtual.categoria &&
      filtroAtual.categoria !== "__ao_vivo" &&
      filtroAtual.categoria !== "__sob_demanda" &&
      !metas.some((meta) => meta.id === filtroAtual.categoria)
    ) {
      filtroAtual.categoria = "";
    }

    secao.hidden = metas.length === 0;
    grade.innerHTML = metas
      .map((meta) => {
        const qtd = contagem.get(meta.id) || 0;
        const live = aoVivoPorCategoria.get(meta.id) || 0;
        const detalhe = `${fmt.format(qtd)} ${qtd === 1 ? "canal" : "canais"}${
          live ? ` · ${fmt.format(live)} ao vivo` : ""
        }`;
        return `
          <button class="category-card" type="button" data-category-card="${escapeHtml(meta.id)}"
                  style="--cat-color:${escapeHtml(meta.cor)}" title="${escapeHtml(meta.descricao)}">
            <span class="category-icon" aria-hidden="true">${escapeHtml(meta.icone)}</span>
            <span class="category-info">
              <strong>${escapeHtml(meta.nome)}</strong>
              <small>${detalhe}</small>
            </span>
            <span class="category-arrow" aria-hidden="true">→</span>
          </button>`;
      })
      .join("");

    if (resumo) {
      resumo.textContent = `${metas.length} ${metas.length === 1 ? "categoria" : "categorias"} · ${fmt.format(total)} canais`;
    }

    // Chips de categoria, na mesma ordem dos cards.
    metas.forEach((meta) => {
      const qtd = contagem.get(meta.id) || 0;
      const botao = document.createElement("button");
      botao.type = "button";
      botao.className = "category-filter category-chip";
      botao.dataset.categoryFilter = meta.id;
      botao.dataset.catChip = "1";
      botao.style.setProperty("--cat-color", meta.cor);
      botao.textContent = `${meta.nome} (${fmt.format(qtd)})`;
      filtros.appendChild(botao);
    });

    atualizarChipsAtivos();
  }

  function atualizarChipsAtivos() {
    document.querySelectorAll("[data-category-filter]").forEach((btn) => {
      btn.classList.toggle(
        "active",
        (btn.dataset.categoryFilter || "") === (filtroAtual.categoria || "")
      );
    });
  }

  /* --------------------------------------------------------------- ao vivo */
  function renderAoVivo() {
    const secao = document.querySelector("[data-live-section]");
    const trilho = document.querySelector("[data-live-rail]");
    if (!secao || !trilho) return;

    const canais = (window.CANAIS_DATA && window.CANAIS_DATA.canais) || [];
    const visiveis = window.CANAIS_ADULTOS
      ? canais
      : canais.filter((c) => !window.canaisEhAdulto(c));
    const aoVivo = visiveis.filter((c) => c.aoVivo !== false).slice(0, LIMITE_AO_VIVO);
    secao.hidden = aoVivo.length === 0;
    trilho.innerHTML = aoVivo.map(cardHTML).join("");
    ligarFallbackLogos(trilho);
  }

  /* -------------------------------------------------------- grade de canais */
  function renderGrade() {
    const grade = document.querySelector("[data-channel-grid]");
    const dados = window.CANAIS_DATA;
    if (!grade || !dados) return;

    const todos = canaisFiltrados();
    const visiveis = todos.slice(0, limiteGrade);

    grade.innerHTML = visiveis.map(cardHTML).join("");
    ligarFallbackLogos(grade);

    const visiveisTodos = window.CANAIS_ADULTOS
      ? dados.canais
      : dados.canais.filter((c) => !window.canaisEhAdulto(c));
    const total = visiveisTodos.length;
    const aoVivoTotal = visiveisTodos.filter((c) => c.aoVivo !== false).length;
    const totalPlaylists = (window.CANAIS_EXTRA_PLAYLISTS || []).length;

    const contador = document.getElementById("contador-canais");
    if (contador) contador.textContent = fmt.format(total);

    const heroLive = document.querySelector("[data-hero-live]");
    if (heroLive) heroLive.textContent = fmt.format(aoVivoTotal);

    const heroPlaylists = document.querySelector("[data-hero-playlists]");
    if (heroPlaylists) heroPlaylists.textContent = fmt.format(totalPlaylists);

    const semResultado = document.querySelector("[data-no-results]");
    if (semResultado) {
      const carregando = !window.CANAIS_CATALOGO_PRONTO;
      semResultado.hidden = !carregando && todos.length !== 0;
      semResultado.textContent = carregando
        ? "Carregando seus canais..."
        : total === 0
          ? "Nenhum canal por aqui ainda. Adicione sua primeira playlist acima."
          : "Nenhum canal encontrado para esse filtro.";
    }

    const botaoMais = document.querySelector("[data-load-more]");
    if (botaoMais) {
      const restantes = Math.max(0, todos.length - visiveis.length);
      botaoMais.hidden = restantes === 0;
      if (restantes) botaoMais.textContent = `Mostrar mais canais (${fmt.format(restantes)} restantes)`;
    }

    atualizarChipsAtivos();
  }

  function renderTudo() {
    renderCategorias();
    renderAoVivo();
    renderGrade();
  }

  window.CanaisRenderGrade = renderGrade;
  window.CanaisRenderTudo = renderTudo;

  window.CanaisFiltrar = function (texto, categoria) {
    filtroAtual = { texto: texto || "", categoria: categoria || "" };
    limiteGrade = LIMITE_GRADE;
    renderGrade();
  };

  window.CanaisSelecionarCategoria = function (id, rolar = true) {
    filtroAtual = { texto: filtroAtual.texto || "", categoria: id || "" };
    limiteGrade = LIMITE_GRADE;
    atualizarChipsAtivos();
    renderGrade();
    if (rolar) {
      const alvo = document.getElementById("canais");
      if (alvo) alvo.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  };

  /* ---------------------------------------------------------------- busca */
  function initBusca() {
    const overlay = document.querySelector("[data-search-overlay]");
    const input = document.querySelector("[data-global-search]");
    const results = document.querySelector("[data-search-results]");
    const aberturas = document.querySelectorAll("[data-search-open], [data-search-open-mobile], [data-search-open-hero]");
    const fechar = document.querySelector("[data-search-close]");
    if (!overlay || !input || !results) return;

    const abrir = () => {
      overlay.classList.add("open");
      overlay.setAttribute("aria-hidden", "false");
      document.body.classList.add("search-open");
      setTimeout(() => input.focus(), 80);
    };

    const fecharOverlay = () => {
      overlay.classList.remove("open");
      overlay.setAttribute("aria-hidden", "true");
      document.body.classList.remove("search-open");
    };

    aberturas.forEach((el) => el.addEventListener("click", abrir));
    aberturas.forEach((el) =>
      el.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          abrir();
        }
      })
    );
    fechar && fechar.addEventListener("click", fecharOverlay);
    overlay.addEventListener("click", (e) => {
      if (e.target === overlay) fecharOverlay();
    });

    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") fecharOverlay();
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        abrir();
      }
    });

    let timer;
    input.addEventListener("input", () => {
      clearTimeout(timer);
      const q = input.value.trim();
      if (q.length < 2) {
        results.innerHTML = "";
        return;
      }
      timer = setTimeout(async () => {
        results.innerHTML = '<div class="search-loading">Buscando canais...</div>';
        try {
          const itens = await CanaisAPI.buscar(q);
          if (!itens.length) {
            results.innerHTML = '<div class="search-loading">Nenhum canal encontrado.</div>';
            return;
          }
          results.innerHTML = itens
            .map(
              (i) =>
                `<a class="search-result" href="${escapeHtml(i.link)}"><strong>${escapeHtml(i.titulo)}</strong>` +
                `<span class="go">Assistir agora →</span></a>`
            )
            .join("");
        } catch (_) {
          results.innerHTML = '<div class="search-loading">Não foi possível buscar agora.</div>';
        }
      }, 220);
    });
  }

  /* ------------------------------------------------------ filtro de canais */
  function initFiltroCanais() {
    const input = document.querySelector("[data-channel-filter]");
    const filtros = document.getElementById("filtros");
    if (!input || !filtros) return;

    const aplicar = () => window.CanaisFiltrar(input.value, filtroAtual.categoria);

    let timer;
    input.addEventListener("input", () => {
      clearTimeout(timer);
      timer = setTimeout(aplicar, 120);
    });

    filtros.addEventListener("click", (evento) => {
      const btn = evento.target.closest("[data-category-filter]");
      if (!btn) return;
      window.CanaisFiltrar(input.value, btn.dataset.categoryFilter || "");
    });

    const filtroAoVivo = document.querySelector("[data-filter-live]");
    if (filtroAoVivo) {
      filtroAoVivo.addEventListener("click", () => {
        window.CanaisSelecionarCategoria("__ao_vivo");
      });
    }

    const grade = document.querySelector("[data-category-grid]");
    if (grade) {
      grade.addEventListener("click", (evento) => {
        const card = evento.target.closest("[data-category-card]");
        if (card) window.CanaisSelecionarCategoria(card.dataset.categoryCard);
      });
    }

    const botaoMais = document.querySelector("[data-load-more]");
    if (botaoMais) {
      botaoMais.addEventListener("click", () => {
        limiteGrade += LIMITE_GRADE;
        renderGrade();
      });
    }

    window.CanaisAplicarFiltro = aplicar;
  }

  /* ------------------------------------------------------ canais 18+ (ocultos)
     A categoria fica escondida: some da grade, da busca e dos chips. O
     botao discreto do rodape libera (e volta a esconder) quando o usuario
     quiser. A escolha fica salva neste navegador. */
  function initAdultos() {
    const botao = document.querySelector("[data-adultos-toggle]");
    if (!botao) return;
    const canais = (window.CANAIS_DATA && window.CANAIS_DATA.canais) || [];
    const quantos = canais.filter((c) => window.canaisEhAdulto(c)).length;
    botao.hidden = quantos === 0;
    if (!quantos) return;
    botao.setAttribute("aria-pressed", window.CANAIS_ADULTOS ? "true" : "false");
    botao.title = window.CANAIS_ADULTOS
      ? "Ocultar os canais 18+"
      : `Mostrar os canais 18+ (${quantos})`;
  }

  function ligarBotaoAdultos() {
    const botao = document.querySelector("[data-adultos-toggle]");
    const msg = document.querySelector("[data-adultos-msg]");
    if (!botao || botao.dataset.pronto) return;
    botao.dataset.pronto = "1";
    botao.addEventListener("click", () => {
      const ligando = !window.CANAIS_ADULTOS;
      window.CANAIS_LIBERAR_ADULTOS(ligando);
      initAdultos();
      if (!msg) return;
      msg.hidden = false;
      msg.textContent = ligando ? "canais 18+ visíveis" : "canais 18+ ocultos";
      clearTimeout(Number(msg.dataset.timer) || 0);
      msg.dataset.timer = String(
        setTimeout(() => {
          msg.hidden = true;
        }, 2600)
      );
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    initBusca();
    initFiltroCanais();
    ligarBotaoAdultos();
    initAdultos();
    renderTudo();
  });

  document.addEventListener("eftv:catalogo-pronto", () => {
    initAdultos();
    renderTudo();
  });
})();
