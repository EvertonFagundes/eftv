// ============================================================
// EFTV — Landing Page (interatividade)
// ============================================================

(() => {
  "use strict";

  // Canais mock para a pré-visualização do catálogo
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
    { nome: "Cartoon Network", categoria: "infantil", aoVivo: false },
    { nome: "Discovery Kids", categoria: "infantil", aoVivo: false },
    { nome: "Gloob", categoria: "infantil", aoVivo: false },
    { nome: "Netflix", categoria: "series", aoVivo: false },
    { nome: "Amazon Prime", categoria: "series", aoVivo: false },
    { nome: "Disney+", categoria: "series", aoVivo: false },
  ];

  const grid = document.getElementById("channels-grid");
  const chips = document.querySelectorAll(".chip");

  function render(filtro = "todos") {
    grid.innerHTML = "";
    const lista = filtro === "todos"
      ? canais
      : canais.filter((c) => c.categoria === filtro);

    lista.forEach((c) => {
      const el = document.createElement("div");
      el.className = "ch-item";
      el.dataset.name = c.nome;
      if (c.aoVivo) {
        el.innerHTML = '<span class="ch-badge">AO VIVO</span>';
      }
      grid.appendChild(el);
    });
  }

  chips.forEach((chip) => {
    chip.addEventListener("click", () => {
      chips.forEach((c) => c.classList.remove("active"));
      chip.classList.add("active");
      render(chip.dataset.cat);
    });
  });

  render();

  // Smooth scroll para links internos
  document.querySelectorAll('a[href^="#"]').forEach((anchor) => {
    anchor.addEventListener("click", function (e) {
      const id = this.getAttribute("href");
      if (id.startsWith("#") && document.querySelector(id)) {
        e.preventDefault();
        document.querySelector(id).scrollIntoView({ behavior: "smooth" });
      }
    });
  });
})();