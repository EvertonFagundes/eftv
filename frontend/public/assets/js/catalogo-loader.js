/* EFTV - carrega o catálogo do servidor local sem bloquear a página.
   No GitHub Pages (modo estático), o static-store.js cuida do IndexedDB. */

(function () {
  if (window.CANAIS_MODO === "estatico" || window.CANAIS_STATIC) {
    window.CANAIS_STATIC = true;
    return;
  }

  function concluir() {
    window.CANAIS_CATALOGO_PRONTO = true;
    document.dispatchEvent(new CustomEvent("eftv:catalogo-pronto"));
  }

  fetch("/api/catalogo.json", { cache: "no-store" })
    .then(function (resp) {
      if (!resp.ok) throw new Error("HTTP " + resp.status);
      return resp.json();
    })
    .then(function (dados) {
      if (!dados || dados.ok === false || !window.CanaisAplicarCatalogo) {
        throw new Error("catálogo inválido");
      }
      window.CanaisAplicarCatalogo(dados);
    })
    .catch(function (erro) {
      console.error("EFTV: não foi possível carregar o catálogo local.", erro);
    })
    .finally(concluir);
})();
