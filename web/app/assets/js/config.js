/* ============================================================
   EFTV — Configuração da versão web/PWA
   Ajuste a URL da API para o seu backend real.
   ============================================================ */

window.EFTV_CONFIG = {
  // Backend FastAPI (Render). Troque para https://api.eftv.com.br em produção.
  API_URL: localStorage.getItem("eftv_api_url") || "https://eftv.onrender.com",

  // Versão exibida no app. Atualizações do PWA são tratadas pelo service worker.
  APP_VERSION: "1.2.0",

  // Proxy opcional (server.py local ou um proxy HTTPS próprio).
  // Ex.: "http://127.0.0.1:8124" quando a página também é http.
  // Em GitHub Pages (https) deixe vazio: o navegador bloqueia http local.
  // O app detecta sozinho o server.py na mesma origem ou em localhost http.
  PROXY_URL: "",

  // URL da playlist licenciada embutida no build (opcional).
  // No app Android de release fica vazia: a URL vem do backend em
  // /player/playlist depois do login. Em builds privados/self-hosted, pode
  // ser preenchida aqui para o app baixar a lista automaticamente.
  // NUNCA comite credenciais do provedor: em repositório público, deixe vazio.
  PLAYLIST_URL: "",

  // Quando true, se a API não responder, o app usa dados de demonstração.
  // Em produção fica false: falha de rede mantém o catálogo salvo e mostra
  // erro, em vez de exibir conteúdo de exemplo para um assinante.
  DEMO_FALLBACK: false,

  // Libera o modo demonstração explícito (?demo=1), útil para a landing e
  // para testar a interface sem backend.
  DEMO_MODE: true,

  // Intervalo do heartbeat de sessão de player (o backend expira em 120s).
  HEARTBEAT_MS: 45000,

  // Salva progresso de filmes/séries a cada N segundos.
  PROGRESS_SAVE_MS: 5000,

  // Limite de itens por página do catálogo.
  PAGE_SIZE: 60,

  // Nome do aparelho enviado no X-Device-Id (hash local).
  DEVICE_PREFIX: "eftv-web",

  // Aviso de fim do teste grátis (uma vez por dia nos últimos N dias).
  TRIAL_NUDGE_DAYS: 3,
};