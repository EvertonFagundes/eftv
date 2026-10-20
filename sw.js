/* EFTV - service worker do PWA.
   Guarda o app shell para abrir offline. Nunca intercepta /api/ no modo local,
   porque o catálogo contém dados da playlist do usuário; a única exceção é o
   api/modo.js, que é público e pequeno. */

const CACHE = "eftv-v4";

const CORE = [
  "./",
  "./index.html",
  "./canal.html",
  "./manifest.webmanifest",
  "./api/modo.js",
  "./assets/css/style.css",
  "./assets/js/data.js",
  "./assets/js/catalogo-base.js",
  "./assets/js/catalogo-loader.js",
  "./assets/js/static-store.js",
  "./assets/js/app.js",
  "./assets/js/canal.js",
  "./assets/js/playlists.js",
  "./assets/js/pwa.js",
  "./embed/player.html",
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

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;

  let url;
  try {
    url = new URL(request.url);
  } catch (_) {
    return;
  }

  // Não intercepta CDNs, streams externos, vídeo/áudio nem dados de playlist.
  if (url.origin !== self.location.origin) return;
  if (request.headers.has("range")) return;
  if (request.destination === "video" || request.destination === "audio") return;
  if (url.pathname.includes("/data/")) return;

  // api/modo.js é público e pode ser cacheado; as demais rotas /api/ contêm
  // dados locais e ficam sempre fora do service worker.
  if (url.pathname.endsWith("/api/modo.js")) {
    event.respondWith(networkFirst(request));
    return;
  }
  if (url.pathname.includes("/api/")) return;

  if (request.mode === "navigate") {
    event.respondWith(networkFirst(request, "./index.html"));
    return;
  }

  event.respondWith(networkFirst(request));
});
