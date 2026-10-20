/* EFTV - base compartilhada do catálogo.
   Prepara a função que mescla os canais importados com os dados base do site.
   O catálogo em si é carregado de forma assíncrona (local) ou pelo IndexedDB
   (GitHub Pages), para não bloquear a abertura da página. */

(function () {
  if (!window.CANAIS_DATA) return;

  if (!window.CANAIS_BASE) {
    window.CANAIS_BASE = {
      canais: (window.CANAIS_DATA.canais || []).slice(),
      categorias: (window.CANAIS_DATA.categorias || []).slice(),
    };
  }

  if (!window.CANAIS_EXTRA) {
    window.CANAIS_EXTRA = { playlists: [], categorias: [], canais: [] };
  }
  if (!Array.isArray(window.CANAIS_EXTRA_PLAYLISTS)) {
    window.CANAIS_EXTRA_PLAYLISTS = [];
  }
  if (typeof window.CANAIS_CATALOGO_PRONTO === "undefined") {
    window.CANAIS_CATALOGO_PRONTO = false;
  }

  window.CanaisAplicarCatalogo = function (novo) {
    var base = window.CANAIS_BASE;
    var categorias = base.categorias.slice();
    (novo.categorias || []).forEach(function (cat) {
      if (!categorias.some(function (c) { return c.id === cat.id; })) categorias.push(cat);
    });
    window.CANAIS_DATA.categorias = categorias;
    window.CANAIS_DATA.canais = base.canais.concat(novo.canais || []);
    window.CANAIS_EXTRA_PLAYLISTS = novo.playlists || [];
    window.CANAIS_CATALOGO_PRONTO = true;
  };
})();
