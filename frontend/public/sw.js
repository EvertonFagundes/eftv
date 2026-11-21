/* EFTV - service worker da SPA do assinante.
   Guarda as páginas e os módulos do app para abrir offline. Nunca intercepta
   /api/ (dados do assinante) e deixa streams de vídeo passarem direto. */

const CACHE = "eftv-spa-v1";

const CORE = [
  "./",
  "./index.html",
  "./login.html",
  "./register.html",
  "./plans.html",
  "./account.html",
  "./player.html",
  "./manifest.webmanifest",
  "./assets/css/style.css",
  "./assets/js/api.js",
  "./assets/js/auth.js",
  "./assets/js/account.js",
  "./assets/js/account-page.js",
  "./assets/js/auth-page.js",
  "./assets/js/main.js",
  "./assets/js/plans-page.js",
  "./assets/js/utils.js",
  "./assets/js/pwa.js",
  "./assets/img/favicon.svg",
  "./assets/img/eftv-mark.svg",
  "./assets/img/icon-192.png",
  "./assets/img/icon-512.png",
  "./assets/img/icon-maskable-512.png",
  "./assets/img/apple-touch-icon.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE).then(async (cache) => {
      await Promise.all(
        CORE.map(async (url) => {
          try {
            await cache.add(url);
          } catch (_) {
            // Um asset opcional pode falhar; o restante do app continua válido.
          }
        })
      );
      await self.skipWaiting();
    })
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(keys.filter((key) => key !== CACHE).map((key) => caches.delete(key)))
      )
      .then(() => self.clients.claim())
  );
});

self.addEventListener("message", (event) => {
  if (event.data === "SKIP_WAITING" || event.data === "skipWaiting") {
    self.skipWaiting();
  }
});

/* Páginas: rede primeiro para sempre pegar a versão publicada, com cache como
   reserva quando estiver offline. */
async function networkFirst(request, fallback) {
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
    if (fallback) {
      const fallbackSalvo = await cache.match(fallback);
      if (fallbackSalvo) return fallbackSalvo;
    }
    return Response.error();
  }
}

/* Módulos, CSS e ícones: responde do cache e atualiza em segundo plano. */
async function staleWhileRevalidate(request) {
  const cache = await caches.open(CACHE);
  const salvo = await cache.match(request);
  const rede = fetch(request)
    .then((resposta) => {
      if (resposta && resposta.ok) {
        cache.put(request, resposta.clone()).catch(() => {});
      }
      return resposta;
    })
    .catch(() => null);
  return salvo || (await rede) || Response.error();
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

  if (url.origin !== self.location.origin) return;
  if (request.headers.has("range")) return;
  if (request.destination === "video" || request.destination === "audio") return;
  // API autenticada nunca entra no cache.
  if (url.pathname.includes("/api/")) return;

  if (request.mode === "navigate") {
    event.respondWith(networkFirst(request, "./index.html"));
    return;
  }

  event.respondWith(staleWhileRevalidate(request));
});
