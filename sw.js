const CACHE = "epyalink-v1";
const SHELL = ["/", "/index.html", "/manifest.json", "/icon-192.png", "/icon-512.png", "/LogoEpyalink.png"];

self.addEventListener("install", event => {
  event.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL)).catch(() => {}));
  self.skipWaiting();
});

self.addEventListener("activate", event => {
  event.waitUntil(
    caches.keys().then(keys => Promise.all(
      keys.filter(k => k !== CACHE).map(k => caches.delete(k))
    ))
  );
  self.clients.claim();
});

self.addEventListener("fetch", event => {
  const req = event.request;
  const url = new URL(req.url);
  if (url.origin !== location.origin || url.pathname.startsWith("/api/") || url.protocol.startsWith("ws")) return;
  if (req.method !== "GET") return;

  // Always prefer the deployed HTML so a new Render deploy is not hidden by an old cache.
  if (req.mode === "navigate" || url.pathname === "/" || url.pathname === "/index.html") {
    event.respondWith(
      fetch(req).then(response => {
        const copy = response.clone();
        caches.open(CACHE).then(c => c.put(req, copy)).catch(() => {});
        return response;
      }).catch(() => caches.match(req).then(cached => cached || caches.match("/index.html") || caches.match("/")))
    );
    return;
  }

  // Static assets: cache first, then refresh the cache when network is available.
  event.respondWith(
    caches.match(req).then(cached => {
      const network = fetch(req).then(response => {
        if (response && response.ok) {
          const copy = response.clone();
          caches.open(CACHE).then(c => c.put(req, copy)).catch(() => {});
        }
        return response;
      }).catch(() => cached);
      return cached || network;
    })
  );
});
