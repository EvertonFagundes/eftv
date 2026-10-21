/* EFTV - dados base da interface.
   Os canais vêm exclusivamente das playlists importadas pelo usuário. */

window.CANAIS_CATEGORIAS = [
  { id: "esportes", nome: "Esportes", icone: "⚽", cor: "#3ee08f", descricao: "Jogos, campeonatos e canais esportivos" },
  { id: "noticias", nome: "Notícias", icone: "📰", cor: "#4fb5ff", descricao: "Jornalismo e cobertura em tempo real" },
  { id: "abertos", nome: "Abertos", icone: "📡", cor: "#71e2ff", descricao: "Canais abertos e afiliadas regionais" },
  { id: "filmes", nome: "Filmes", icone: "🎬", cor: "#a78bfa", descricao: "Longas, lançamentos e clássicos" },
  { id: "series", nome: "Séries", icone: "📺", cor: "#7c9cff", descricao: "Séries, doramas e temporadas completas" },
  { id: "novelas", nome: "Novelas", icone: "💜", cor: "#f472b6", descricao: "Novelas e tramas para maratonar" },
  { id: "documentarios", nome: "Documentários", icone: "🌍", cor: "#2dd4bf", descricao: "Natureza, história, ciência e investigação" },
  { id: "infantil", nome: "Infantil", icone: "🧸", cor: "#fbbf24", descricao: "Desenhos e conteúdo para crianças" },
  { id: "animes", nome: "Animes", icone: "🌀", cor: "#fb923c", descricao: "Animes legendados e dublados" },
  { id: "variedades", nome: "Variedades", icone: "✨", cor: "#e879f9", descricao: "Shows, realities e programas de TV" },
  { id: "musica", nome: "Música", icone: "🎵", cor: "#f472b6", descricao: "Música, clipes e apresentações" },
  { id: "religiosos", nome: "Religiosos", icone: "🙏", cor: "#fcd34d", descricao: "Conteúdo religioso e programação de fé" },
  { id: "24h", nome: "24 Horas", icone: "🕘", cor: "#60a5fa", descricao: "Canais com programação contínua" },
  { id: "streaming", nome: "Streaming", icone: "▶️", cor: "#818cf8", descricao: "Canais de serviços de streaming" },
  { id: "adultos", nome: "Adultos", icone: "🔞", cor: "#f87171", descricao: "Conteúdo adulto (18+)" },
  { id: "outros", nome: "Outros", icone: "🗂️", cor: "#94a3b8", descricao: "Canais que não se encaixam nas demais categorias" },
];

window.CANAIS_DATA = {
  site: {
    nome: "EFTV",
    tagline: "Seus canais, ao vivo e sob demanda, em um só lugar.",
  },
  categorias: window.CANAIS_CATEGORIAS.map(({ id, nome }) => ({ id, nome })),
  canais: [],
};

/* Normaliza texto para busca (sem acentos). */
window.canaisNormalize = function (valor = "") {
  return valor.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase().trim();
};

/* Define a categoria principal a partir do group-title da playlist.
   A mesma regra existe no server.py para o catálogo local. */
window.canaisCategoria = function (grupo = "") {
  const g = window.canaisNormalize(grupo).replace(/\s+/g, " ");
  if (!g) return "outros";
  if (g.includes("adult") || g.includes("xxx") || g.includes("bella da semana") || g.includes("18+")) {
    return "adultos";
  }
  if (g.startsWith("filme")) {
    return g.includes("infantil") ? "infantil" : "filmes";
  }
  if (g.startsWith("serie")) {
    return g.includes("crunchyroll") || g.includes("anime") ? "animes" : "series";
  }
  if (g.startsWith("canais")) {
    if (/(esport|espn|sportv|premiere|jogos do dia|campeonatos estaduais|ppv|nba|dazn|liga futsal)/.test(g)) return "esportes";
    if (g.includes("noticia")) return "noticias";
    if (g.includes("abertos") || g.includes("globos") || g.includes("recordtv")) return "abertos";
    if (/(hbo|telecine|paramount|max|prime video|disney|apple tv)/.test(g)) return "streaming";
    if (g.includes("[24h] series")) return "series";
    if (g.includes("[24h] desenhos")) return "infantil";
    if (g.includes("[24h] animes")) return "animes";
    if (g.includes("[24h] musicas")) return "musica";
    if (g.includes("[24h] outros")) return "24h";
    if (g.includes("24 horas")) return "24h";
    if (g.includes("infantis")) return "infantil";
    if (g.includes("religiosos")) return "religiosos";
    if (g.includes("documentarios")) return "documentarios";
    if (g.includes("variedades") || g.includes("reality") || g.includes("[24h] youtube") || g.includes("[24h] pegadinhas")) return "variedades";
    if (g.includes("filmes e series") || g.includes("legendados")) return "filmes";
    if (g.includes("adultos")) return "adultos";
    return "outros";
  }
  if (g.includes("esport")) return "esportes";
  if (g.includes("noticia")) return "noticias";
  if (g.includes("documentari")) return "documentarios";
  if (g.includes("novela")) return "novelas";
  if (g.includes("anime")) return "animes";
  if (g.includes("infantil") || g.includes("desenho")) return "infantil";
  if (g.includes("religios")) return "religiosos";
  if (g.includes("musica")) return "musica";
  if (/(show|stand up|programas de tv|reels|shorts)/.test(g)) return "variedades";
  return "outros";
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

/* Oculta senhas/tokens na exibição do link da playlist. O botão "Copiar link"
   continua copiando o endereço completo. */
window.canaisMascararUrl = function (valor = "") {
  return String(valor).replace(
    /([?&](?:username|user|password|pass|senha|token|key|auth)=)([^&]*)/gi,
    (_, chave, segredo) => chave + (segredo ? "••••••" : "")
  );
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

/* ------------------------------------------------------- canais 18+ (adultos)
   Ficam ocultos por padrao: somem da grade, da busca e dos chips de
   categoria. O usuario libera explicitamente pelo botao discreto do
   rodape, e a escolha fica salva neste navegador. */
window.CANAIS_ADULTOS = (function () {
  try {
    return localStorage.getItem("eftv-adultos") === "1";
  } catch (_) {
    return false;
  }
})();

window.CANAIS_LIBERAR_ADULTOS = function (ligar) {
  window.CANAIS_ADULTOS = !!ligar;
  try {
    localStorage.setItem("eftv-adultos", ligar ? "1" : "0");
  } catch (_) {
    // Navegador sem armazenamento: vale so para esta sessao.
  }
  if (typeof window.CanaisRenderTudo === "function") window.CanaisRenderTudo();
  document.dispatchEvent(new CustomEvent("eftv:adultos"));
  return window.CANAIS_ADULTOS;
};

/* Reconhece um canal 18+ pela categoria ou pelo grupo da playlist. */
window.canaisEhAdulto = function (canal) {
  if (!canal) return false;
  if ((canal.categoria || "") === "adultos") return true;
  const grupo = window.canaisNormalize
    ? window.canaisNormalize(canal.grupo || "")
    : String(canal.grupo || "").toLowerCase();
  return /adult|xxx|18\+|bella da semana/.test(grupo);
};
