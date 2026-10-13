/* PRUDENT TECH service worker.
   - Opens the app instantly and shows a friendly page when there is no connection.
   - Pages and files: network first (always the newest version when online), saved copy when offline or slow.
   - Product lists, product pages and categories: the last copy seen is kept so you can still browse offline.
   - Never saved: accounts, carts, orders, payments, reviews, prices at checkout, the admin dashboard.
   Change VERSION to make every phone throw away its saved copies on the next visit. */
const VERSION = "v1";
const STATIC = `pt-static-${VERSION}`;
const API = `pt-api-${VERSION}`;
const API_MAX_ENTRIES = 60;
const PRECACHE = ["/", "/offline.html", "/theme.css", "/store.css", "/config.js", "/app.js", "/pwa.js", "/manifest.webmanifest", "/icons/icon-192.png"];
const API_PATHS = [/^\/products(\/[^/]+)?$/, /^\/categories$/, /^\/brands$/, /^\/banners$/];

/* What kind of request is this? Anything not listed is left alone (the browser handles it normally). */
function classify(request, url) {
  if (request.method !== "GET") return "skip";
  if (url.origin !== self.location.origin) return "skip";
  const p = url.pathname;
  if (p.startsWith("/admin") || p === "/sw.js") return "skip";
  if (request.mode === "navigate") return p === "/" || p.endsWith(".html") ? "page" : "skip";
  if (API_PATHS.some((re) => re.test(p))) return "api";
  if (p.startsWith("/icons/")) return "icon";
  if (/\.(?:js|css|webmanifest|html)$/.test(p)) return "asset";
  return "skip";
}

const withTimeout = (promise, ms) =>
  new Promise((resolve, reject) => {
    const t = setTimeout(() => reject(new Error("timeout")), ms);
    promise.then((v) => { clearTimeout(t); resolve(v); }, (e) => { clearTimeout(t); reject(e); });
  });

async function trim(cache, max) {
  const keys = await cache.keys();
  for (let i = 0; i < keys.length - max; i++) await cache.delete(keys[i]);
}

async function networkFirst(event, cacheName, key, timeoutMs, maxEntries) {
  const cache = await caches.open(cacheName);
  const fresh = fetch(event.request).then((res) => {
    if (res.ok) cache.put(key, res.clone()).then(() => maxEntries && trim(cache, maxEntries)).catch(() => {});
    return res;
  });
  event.waitUntil(fresh.catch(() => {})); // keep updating the saved copy even if we already answered from it
  try {
    const res = await withTimeout(fresh, timeoutMs);
    if (res.status >= 500) { const saved = await cache.match(key); if (saved) return saved; }
    return res;
  } catch (err) {
    const saved = await cache.match(key);
    if (saved) return saved;
    return fresh; // nothing saved: wait for the network (fails when offline)
  }
}

async function cacheFirst(event, cacheName, key) {
  const cache = await caches.open(cacheName);
  const hit = await cache.match(key);
  if (hit) return hit;
  const res = await fetch(event.request);
  if (res.ok) cache.put(key, res.clone());
  return res;
}

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(STATIC).then((c) => c.addAll(PRECACHE.map((u) => new Request(u, { cache: "reload" })))));
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((names) => Promise.all(names.filter((n) => n.startsWith("pt-") && n !== STATIC && n !== API).map((n) => caches.delete(n))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("message", (event) => {
  if (event.data === "SKIP_WAITING") self.skipWaiting(); // sent when the customer taps "Refresh" on the update notice
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  const kind = classify(event.request, url);
  if (kind === "skip") return;
  const pageKey = new Request(url.origin + url.pathname); // ?slug=... and other query strings share one saved page

  if (kind === "page") {
    event.respondWith(
      networkFirst(event, STATIC, pageKey, 3500).catch(async () => (await caches.match("/offline.html")) || Response.error())
    );
  } else if (kind === "asset") {
    event.respondWith(networkFirst(event, STATIC, pageKey, 4000));
  } else if (kind === "icon") {
    event.respondWith(cacheFirst(event, STATIC, pageKey));
  } else if (kind === "api") {
    event.respondWith(networkFirst(event, API, event.request.url, 6000, API_MAX_ENTRIES));
  }
});
