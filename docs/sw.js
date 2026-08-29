/* Minimal service worker: cache the app shell for install/offline, but NEVER
   cache job data — freshness is the whole point of this app. */
const SHELL = "job-scanner-shell-v2";
const ASSETS = ["./", "index.html", "style.css", "app.js", "icon.svg", "manifest.json"];

self.addEventListener("install", e => {
  e.waitUntil(caches.open(SHELL).then(c => c.addAll(ASSETS)));
  self.skipWaiting();
});

self.addEventListener("activate", e => {
  e.waitUntil(caches.keys().then(keys =>
    Promise.all(keys.filter(k => k !== SHELL).map(k => caches.delete(k)))
  ).then(() => self.clients.claim()));
});

self.addEventListener("fetch", e => {
  const url = new URL(e.request.url);
  if (url.pathname.includes("/data/")) return;   // network only, always fresh
  // "no-cache" forces revalidation against GitHub Pages' 10-min HTTP cache,
  // so UI updates appear on the next reload instead of lagging behind.
  e.respondWith(
    fetch(e.request, { cache: "no-cache" }).then(r => {
      const copy = r.clone();
      caches.open(SHELL).then(c => c.put(e.request, copy));
      return r;
    }).catch(() => caches.match(e.request))
  );
});
