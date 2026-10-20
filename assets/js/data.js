/* EFTV - dados base da interface.
   Os canais vêm exclusivamente das playlists importadas pelo usuário. */

window.CANAIS_DATA = {
  site: {
    nome: "EFTV",
    tagline: "Seus canais, ao vivo e sob demanda, em um só lugar.",
  },
  categorias: [{ id: "importados", nome: "Importados" }],
  canais: [],
};

/* Normaliza texto para busca (sem acentos). */
window.canaisNormalize = function (valor = "") {
  return valor.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase().trim();
};

/* Escapa texto vindo de playlists (conteúdo não confiável) antes de entrar
   em innerHTML. */
window.canaisEscape = function (valor = "") {
  return String(valor)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
};

/* Iniciais usadas como logo alternativa quando o canal não tem tvg-logo. */
window.canaisIniciais = function (nome = "") {
  const partes = String(nome)
    .replace(/[^\p{L}\p{N} ]/gu, " ")
    .trim()
    .split(/\s+/)
    .filter(Boolean);
  if (!partes.length) return "TV";
  if (partes.length === 1) return partes[0].slice(0, 2).toUpperCase();
  return (partes[0][0] + partes[partes.length - 1][0]).toUpperCase();
};

window.canaisLogoFallback = function (nome = "") {
  const iniciais = window.canaisEscape(window.canaisIniciais(nome));
  const svg =
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 320 180">` +
    `<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">` +
    `<stop offset="0" stop-color="#0d2038"/><stop offset="1" stop-color="#071426"/>` +
    `</linearGradient></defs>` +
    `<rect width="320" height="180" fill="url(#g)"/>` +
    `<text x="160" y="104" text-anchor="middle" font-family="Arial, sans-serif" ` +
    `font-size="58" font-weight="700" fill="#5fa8ff">${iniciais}</text></svg>`;
  return "data:image/svg+xml;charset=utf-8," + encodeURIComponent(svg);
};
