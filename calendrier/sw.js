// Calendrier Gerzat : garde une copie de la page et des plans pour marcher sans réseau.
// Réseau d'abord (toujours la dernière version), copie locale si pas de réseau.
const CACHE = "calendrier-V8";
const PRE = ["./", "index.html", "config.js", "suivi.html", "logo.png", "favicon.png", "apple-touch-icon.png", "snapshot.json",
  "gerzat.json", "gerzat-plan.json", "gerzat-zones.json", "gerzat-poi.json",
  "aulnat.json", "aulnat-plan.json", "aulnat-zones.json", "aulnat-poi.json",
  "malintrat.json", "malintrat-plan.json", "malintrat-zones.json", "malintrat-poi.json"];

self.addEventListener("install", e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(PRE)).then(() => self.skipWaiting()));
});
self.addEventListener("activate", e => {
  e.waitUntil(caches.keys()
    .then(k => Promise.all(k.filter(n => n.startsWith("calendrier-") && n !== CACHE).map(n => caches.delete(n))))
    .then(() => self.clients.claim()));
});
self.addEventListener("fetch", e => {
  const u = new URL(e.request.url);
  if (e.request.method !== "GET" || u.origin !== location.origin) return;
  e.respondWith(
    fetch(e.request).then(r => {
      if (r.ok) { const copie = r.clone(); caches.open(CACHE).then(c => c.put(e.request, copie)); }
      return r;
    }).catch(() => caches.match(e.request, { ignoreSearch: true })
      .then(r => r || (e.request.mode === "navigate" ? caches.match("./") : undefined))
      .then(r => r || new Response("Hors ligne", { status: 503, headers: { "Content-Type": "text/plain; charset=utf-8" } })))
  );
});
