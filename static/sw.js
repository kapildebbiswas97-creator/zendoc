const STATIC_CACHE = "zendoc-static-v6-launch-refresh-20260924";
const STATIC_ASSETS = [
  "/static/style.css",
  "/static/ui-polish.css",
  "/static/product-expansion.css",
  "/static/app.js",
  "/static/finder.js",
  "/static/messages_live.js",
  "/static/messages_composer.js",
  "/static/incoming_calls.js",
  "/static/calls.js",
  "/static/edgecare_voice.js",
  "/static/pwa.js",
  "/static/favicon.svg",
  "/offline"
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(STATIC_CACHE)
      .then((cache) => cache.addAll(STATIC_ASSETS))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((key) => key !== STATIC_CACHE).map((key) => caches.delete(key))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;

  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;

  // Never cache API responses or authenticated HTML/health data. Static assets
  // use network-first delivery so a new deployment does not keep serving stale
  // JavaScript/CSS from an older installed PWA; cache is offline fallback only.
  if (url.pathname.startsWith("/api/")) return;

  if (url.pathname.startsWith("/static/")) {
    event.respondWith(
      fetch(request)
        .then((response) => {
          if (!response.ok) return response;
          const copy = response.clone();
          return caches.open(STATIC_CACHE)
            .then((cache) => cache.put(request, copy))
            .then(() => response);
        })
        .catch(() => caches.match(request))
    );
    return;
  }

  // HTML stays network-only to avoid persisting sensitive personalized pages.
  if (request.mode === "navigate") {
    event.respondWith(fetch(request).catch(() => caches.match("/offline")));
  }
});
