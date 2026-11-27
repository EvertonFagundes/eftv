/* ============================================================
   EFTV — Configuração da versão web/PWA
   Ajuste a URL da API para o seu backend real.
   ============================================================ */

window.EFTV_CONFIG = {
  // Backend FastAPI (Render). Troque para https://api.eftv.com.br em produção.
  API_URL: localStorage.getItem("eftv_api_url") || "https://eftv.onrender.com",

  // Versão exibida no app (comparada com /app/version para atualização)
  APP_VERSION: "1.0.0",
  APP_VERSION_CODE: 1,

  // Quando true, se a API não responder, o app usa dados de demonstração.
  // Útil para testar a interface sem backend.
  DEMO_FALLBACK: true,

  // Intervalo do heartbeat de sessão de player (o backend expira em 120s).
  HEARTBEAT_MS: 45000,

  // Salva progresso de filmes/séries a cada N segundos.
  PROGRESS_SAVE_MS: 5000,

  // Limite de itens por página do catálogo.
  PAGE_SIZE: 60,

  // Nome do aparelho enviado no X-Device-Id (hash local).
  DEVICE_PREFIX: "eftv-web",
};