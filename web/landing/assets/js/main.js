// ============================================================
// EFTV — Landing Page (interatividade)
// ============================================================

(() => {
  "use strict";

  const header = document.querySelector(".site-header");
  const nav = document.getElementById("main-nav");
  const navToggle = document.getElementById("nav-toggle");

  // ---------- Header com estado ao rolar ----------

  function atualizarHeader() {
    if (!header) return;
    header.classList.toggle("scrolled", window.scrollY > 8);
  }

  atualizarHeader();
  window.addEventListener("scroll", atualizarHeader, { passive: true });

  // ---------- Menu mobile ----------

  function fecharMenu() {
    if (!nav || !navToggle) return;
    nav.classList.remove("is-open");
    navToggle.setAttribute("aria-expanded", "false");
    navToggle.setAttribute("aria-label", "Abrir menu");
  }

  if (nav && navToggle) {
    navToggle.addEventListener("click", () => {
      const aberto = nav.classList.toggle("is-open");
      navToggle.setAttribute("aria-expanded", String(aberto));
      navToggle.setAttribute("aria-label", aberto ? "Fechar menu" : "Abrir menu");
    });

    nav.querySelectorAll("a").forEach((link) => {
      link.addEventListener("click", fecharMenu);
    });

    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") fecharMenu();
    });

    document.addEventListener("click", (e) => {
      if (!nav.classList.contains("is-open")) return;
      if (nav.contains(e.target) || navToggle.contains(e.target)) return;
      fecharMenu();
    });
  }

  // ---------- Animações de entrada ----------

  const elementosReveal = document.querySelectorAll("[data-reveal]");
  const reduzirMovimento = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  if ("IntersectionObserver" in window && !reduzirMovimento) {
    const observador = new IntersectionObserver(
      (entradas) => {
        entradas.forEach((entrada) => {
          if (!entrada.isIntersecting) return;
          entrada.target.classList.add("is-visible");
          observador.unobserve(entrada.target);
        });
      },
      { threshold: 0.12, rootMargin: "0px 0px -8% 0px" }
    );

    elementosReveal.forEach((el) => observador.observe(el));
  } else {
    elementosReveal.forEach((el) => el.classList.add("is-visible"));
  }

  // ---------- Prévia do catálogo ----------

  const canais = [
    { nome: "Globo", categoria: "tv", aoVivo: true },
    { nome: "Record", categoria: "tv", aoVivo: true },
    { nome: "SBT", categoria: "tv", aoVivo: false },
    { nome: "Band", categoria: "tv", aoVivo: false },
    { nome: "RedeTV", categoria: "tv", aoVivo: false },
    { nome: "GloboNews", categoria: "noticias", aoVivo: true },
    { nome: "CNN Brasil", categoria: "noticias", aoVivo: true },
    { nome: "BandNews", categoria: "noticias", aoVivo: false },
    { nome: "Jovem Pan News", categoria: "noticias", aoVivo: false },
    { nome: "Sportv", categoria: "esportes", aoVivo: true },
    { nome: "Premiere", categoria: "esportes", aoVivo: true },
    { nome: "ESPN", categoria: "esportes", aoVivo: false },
    { nome: "Band Sports", categoria: "esportes", aoVivo: false },
    { nome: "HBO", categoria: "filmes", aoVivo: false },
    { nome: "Telecine", categoria: "filmes", aoVivo: false },
    { nome: "Universal TV", categoria: "filmes", aoVivo: false },
    { nome: "Warner Channel", categoria: "filmes", aoVivo: false },
    { nome: "Discovery", categoria: "docs", aoVivo: false },
    { nome: "History", categoria: "docs", aoVivo: false },
    { nome: "Nat Geo", categoria: "docs", aoVivo: false },
    { nome: "Cartoon Network", categoria: "infantil", aoVivo: false },
    { nome: "Discovery Kids", categoria: "infantil", aoVivo: false },
    { nome: "Gloob", categoria: "infantil", aoVivo: false },
  ];

  const tons = {
    tv: 210,
    esportes: 145,
    noticias: 20,
    filmes: 265,
    docs: 185,
    infantil: 330,
  };

  const grid = document.getElementById("channels-grid");
  const chips = document.querySelectorAll(".chip");

  function render(filtro = "todos") {
    if (!grid) return;

    const lista =
      filtro === "todos"
        ? canais
        : canais.filter((canal) => canal.categoria === filtro);

    grid.innerHTML = "";

    lista.forEach((canal) => {
      const item = document.createElement("article");
      item.className = "ch-item";
      item.style.setProperty("--hue", tons[canal.categoria] ?? 210);
      item.setAttribute("aria-label", canal.nome + (canal.aoVivo ? " — ao vivo" : ""));

      const inicial = document.createElement("span");
      inicial.className = "ch-initial";
      inicial.setAttribute("aria-hidden", "true");
      inicial.textContent = canal.nome.charAt(0);

      const categoria = document.createElement("span");
      categoria.className = "ch-cat";
      categoria.textContent = canal.categoria;

      const nome = document.createElement("span");
      nome.className = "ch-name";
      nome.textContent = canal.nome;

      item.append(inicial, categoria, nome);

      if (canal.aoVivo) {
        const badge = document.createElement("span");
        badge.className = "ch-badge";
        badge.textContent = "AO VIVO";
        item.appendChild(badge);
      }

      grid.appendChild(item);
    });
  }

  chips.forEach((chip) => {
    chip.addEventListener("click", () => {
      chips.forEach((outro) => {
        outro.classList.remove("active");
        outro.setAttribute("aria-pressed", "false");
      });

      chip.classList.add("active");
      chip.setAttribute("aria-pressed", "true");
      render(chip.dataset.cat);
    });
  });

  render();
})();
