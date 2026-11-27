/*======================================================================
  EFTV — Service Worker da versão web (PWA)
  - App shell em cache para abrir rápido e funcionar offline.
  - HTML/JS/CSS: rede primeiro (não fica preso em versão antiga).
  - Ícones/imagens: cache primeiro.
  - Vídeos, áudio, range requests e API: passam direto, sem cache.
  ======================================================================*/

const CACHE = "eftv-web-v3";

const CORE = [
  "./",
  "./index.html",
  "./checkout.html",
  "./assets/css/style.css",
  "./assets/js/config.js",
  "./assets/js/store.js",
  "./assets/js/api.js",
  "./assets/js/playlist.js",
  "./assets/js/catalog.js",
  "./assets/js/player.js",
  "./assets/js/app.js",
  "./assets/js/pwa.js",
  "./manifest.webmanifest",
  "./assets/img/favicon.svg",
  "./assets/img/favicon-32.png",
  "./assets/img/apple-touch-icon.png",
  "./assets/img/icon-192.png",
  "./assets/img/icon-512.png",
  "./assets/img/icon-maskable-512.png",
  "./assets/img/placeholder-poster.svg",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE).then((cache) => {
      return cache.addAll(CORE).catch((err) => {
        console.warn("EFTV SW: falha ao cachear alguns itens iniciais", err);
      });
    }).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys.filter((key) => key !== CACHE).map((key) => caches.delete(key))
      );
    }).then(() => self.clients.claim())
  );
});

async function networkFirst(request) {
  const cache = await caches.open(CACHE);
  try {
    const resposta = await fetch(request);
    if (resposta && resposta.ok) {
      cache.put(request, resposta.clone()).catch(() => {});
    }
    return resposta;
  } catch (_) {
    const salvo = await cache.match(request);
    if (salvo) return salvo;
    return Response.error();
  }
}

async function cacheFirst(request) {
  const salvo = await caches.match(request);
  if (salvo) return salvo;
  try {
    const resposta = await fetch(request);
    if (resposta && resposta.ok) {
      const cache = await caches.open(CACHE);
      cache.put(request, resposta.clone()).catch(() => {});
    }
    return resposta;
  } catch (_) {
    return Response.error();
  }
}

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;

  let url;
  try {
    url = new URL(request.url);
  } catch (_) {
    return;
  }

  // Mesmo domínio apenas.
  if (url.origin !== self.location.origin) return;

  // Vídeo / áudio / range requests: nunca cacheia.
  if (request.headers.has("range")) return;
  if (request.destination === "video" || request.destination === "audio") return;

  // API do backend: nunca cacheia (dados do assinante, tokens, pagamentos).
  if (url.pathname.includes("/api/")) return;

  // Navegação: rede primeiro, com fallback para o cache offline.
  if (request.mode === "navigate") {
    event.respondWith(networkFirst(request));
    return;
  }

  // Código e estilos: rede primeiro para não servir versão antiga.
  if (
    request.destination === "script" ||
    request.destination === "style" ||
    request.destination === "manifest" ||
    url.pathname.endsWith(".webmanifest") ||
    url.pathname.endsWith(".json")
  ) {
    event.respondWith(networkFirst(request));
    return;
  }

  // Ícones, imagens e demais assets: cache primeiro.
  event.respondWith(cacheFirst(request));
});

self.addEventListener("message", (event) => {
  if (event.data === "SKIP_WAITING") {
    self.skipWaiting();
  }
});
