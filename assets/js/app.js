/* EFTV - camada compartilhada: busca, filtros e helpers.
   A grade é montada sobre o catálogo local (playlists importadas), com
   renderização limitada para não travar o navegador em listas grandes. */

(function () {
  const norm = window.canaisNormalize;

  /* ------------------------------------------------------------ "API" local */
  const CanaisAPI = {
    async buscar(query, limite = 8) {
      const q = norm(query);
      if (q.length < 2) return [];
      const dados = window.CANAIS_DATA;
      return dados.canais
        .filter(
          (c) =>
            norm(c.nome).includes(q) ||
            norm(c.categoria).includes(q) ||
            norm(c.grupo || "").includes(q)
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
      return cat ? cat.nome : id;
    },
  };
  window.CanaisAPI = CanaisAPI;

  const escapeHtml = window.canaisEscape;
  const fmt = new Intl.NumberFormat("pt-BR");
  const LIMITE_GRADE = 240;
  let limiteGrade = LIMITE_GRADE;
  let filtroAtual = { texto: "", categoria: "" };

  /* Lista filtrada sobre os dados (não sobre o DOM). Assim a busca e o filtro
     continuam funcionando mesmo quando a grade mostra só uma parte dos canais. */
  function canaisFiltrados() {
    const dados = window.CANAIS_DATA;
    const lista = (dados && dados.canais) || [];
    const q = norm(filtroAtual.texto || "");
    const cat = (filtroAtual.categoria || "").trim();

    let filtrados = lista;
    if (q) {
      filtrados = filtrados.filter((c) => {
        const nome = norm(c.nome || "");
        const grupo = norm(c.grupo || "");
        const categoria = norm(c.categoria || "");
        return nome.includes(q) || grupo.includes(q) || categoria.includes(q);
      });
    }

    if (!cat) return filtrados;
    if (cat === "__ao_vivo") return filtrados.filter((c) => c.aoVivo !== false);
    if (cat === "__sob_demanda") return filtrados.filter((c) => c.aoVivo === false);
    const categoria = norm(cat);
    return filtrados.filter((c) => norm(c.categoria || "") === categoria);
  }

  /* -------------------------------------------------------- grade de canais */
  function renderGrade() {
    const grade = document.querySelector("[data-channel-grid]");
    const dados = window.CANAIS_DATA;
    if (!grade || !dados) return;

    const todos = canaisFiltrados();
    const visiveis = todos.slice(0, limiteGrade);

    grade.innerHTML = visiveis
      .map((c) => {
        const categoriaBase = CanaisAPI.categoriaNome(c.categoria);
        const categoria = c.grupo ? `${categoriaBase} · ${c.grupo}` : categoriaBase;
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
      })
      .join("");

    // Se o logo da playlist estiver quebrado, mostra as iniciais.
    grade.querySelectorAll("img[data-thumb]").forEach((img) => {
      img.addEventListener("error", () => img.remove(), { once: true });
    });

    const total = dados.canais.length;
    const aoVivoTotal = dados.canais.filter((c) => c.aoVivo !== false).length;
    const totalPlaylists = (window.CANAIS_EXTRA_PLAYLISTS || []).length;

    const contador = document.getElementById("contador-canais");
    if (contador) contador.textContent = fmt.format(total);

    const heroLive = document.querySelector("[data-hero-live]");
    if (heroLive) heroLive.textContent = fmt.format(aoVivoTotal);

    const heroPlaylists = document.querySelector("[data-hero-playlists]");
    if (heroPlaylists) heroPlaylists.textContent = fmt.format(totalPlaylists);

    const semResultado = document.querySelector("[data-no-results]");
    if (semResultado) {
      semResultado.hidden = todos.length !== 0;
      semResultado.textContent =
        total === 0
          ? "Nenhum canal por aqui ainda. Adicione sua primeira playlist acima."
          : "Nenhum canal encontrado para esse filtro.";
    }

    const botaoMais = document.querySelector("[data-load-more]");
    if (botaoMais) {
      const restantes = Math.max(0, todos.length - visiveis.length);
      botaoMais.hidden = restantes === 0;
      if (restantes) botaoMais.textContent = `Mostrar mais canais (${fmt.format(restantes)} restantes)`;
    }
  }
  window.CanaisRenderGrade = renderGrade;

  window.CanaisFiltrar = function (texto, categoria) {
    filtroAtual = { texto: texto || "", categoria: categoria || "" };
    limiteGrade = LIMITE_GRADE;
    renderGrade();
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
    const botoes = [...document.querySelectorAll("[data-category-filter]")];
    let categoriaAtiva = "";

    if (!input || !botoes.length) return;

    const aplicar = () => {
      window.CanaisFiltrar(input.value, categoriaAtiva);
    };

    // Debounce: em listas com dezenas de milhares de canais, filtrar a cada
    // tecla fica pesado. 120 ms já parece instantâneo para quem digita.
    let timer;
    input.addEventListener("input", () => {
      clearTimeout(timer);
      timer = setTimeout(aplicar, 120);
    });

    botoes.forEach((btn) =>
      btn.addEventListener("click", () => {
        categoriaAtiva = btn.dataset.categoryFilter || "";
        botoes.forEach((x) => x.classList.toggle("active", x === btn));
        aplicar();
      })
    );

    const botaoMais = document.querySelector("[data-load-more]");
    if (botaoMais) {
      botaoMais.addEventListener("click", () => {
        limiteGrade += LIMITE_GRADE;
        renderGrade();
      });
    }

    window.CanaisAplicarFiltro = aplicar;
    aplicar();
  }

  document.addEventListener("DOMContentLoaded", () => {
    initBusca();
    initFiltroCanais();
  });
})();
