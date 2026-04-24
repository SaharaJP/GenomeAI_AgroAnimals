/* GenomeAI Агро — Service Worker v1 */

const CACHE_VERSION = 'v1';
const STATIC_CACHE = `genomeai-static-${CACHE_VERSION}`;
const API_CACHE = `genomeai-api-${CACHE_VERSION}`;
const PAGES_CACHE = `genomeai-pages-${CACHE_VERSION}`;

const ALL_CACHES = [STATIC_CACHE, API_CACHE, PAGES_CACHE];

const PRECACHE_ASSETS = [
  '/manifest.json',
  '/icons/icon-192.svg',
  '/icons/icon-512.svg',
];

// ── Install ──────────────────────────────────────────────────────────────────
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches
      .open(STATIC_CACHE)
      .then((cache) => cache.addAll(PRECACHE_ASSETS))
      .then(() => self.skipWaiting()),
  );
});

// ── Activate: prune old caches ────────────────────────────────────────────────
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(
          keys
            .filter((k) => !ALL_CACHES.includes(k))
            .map((k) => caches.delete(k)),
        ),
      )
      .then(() => self.clients.claim()),
  );
});

// ── Fetch ────────────────────────────────────────────────────────────────────
self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);

  if (request.method !== 'GET') return;
  // Skip cross-origin requests
  if (url.origin !== self.location.origin) return;
  // Skip Next.js internals
  if (url.pathname.startsWith('/_next/')) return;

  if (url.pathname.startsWith('/api/')) {
    // Network-first for API — fall back to cached response
    event.respondWith(networkFirst(request, API_CACHE, apiOfflineFallback(url)));
    return;
  }

  if (/\.(js|css|png|svg|ico|woff2?|jpg|jpeg|webp|gif)$/.test(url.pathname)) {
    // Cache-first for static assets
    event.respondWith(cacheFirst(request, STATIC_CACHE));
    return;
  }

  // Pages: network-first, store for offline
  event.respondWith(networkFirst(request, PAGES_CACHE, pageFallback()));
});

// ── Strategies ───────────────────────────────────────────────────────────────
async function networkFirst(request, cacheName, fallback) {
  try {
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(cacheName);
      cache.put(request, response.clone());
    }
    return response;
  } catch {
    const cached = await caches.match(request);
    if (cached) return cached;
    return fallback;
  }
}

async function cacheFirst(request, cacheName) {
  const cached = await caches.match(request);
  if (cached) return cached;
  try {
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(cacheName);
      cache.put(request, response.clone());
    }
    return response;
  } catch {
    return new Response('', { status: 503 });
  }
}

function apiOfflineFallback(url) {
  return new Response(
    JSON.stringify({ error: 'offline', message: 'Нет соединения с сервером' }),
    { status: 503, headers: { 'Content-Type': 'application/json' } },
  );
}

function pageFallback() {
  return new Response(
    `<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"/>
  <title>GenomeAI Агро — Нет соединения</title>
  <style>
    body{font-family:system-ui,sans-serif;display:flex;align-items:center;
         justify-content:center;min-height:100vh;margin:0;background:#f7f9fa;color:#0f172a}
    .box{text-align:center;padding:32px;max-width:340px}
    .icon{font-size:48px;margin-bottom:16px}
    h1{font-size:20px;font-weight:700;margin:0 0 8px}
    p{color:#64748b;font-size:14px;margin:0 0 20px}
    a{color:#0d9488;font-weight:500}
  </style>
</head>
<body>
  <div class="box">
    <div class="icon">🌿</div>
    <h1>Нет соединения</h1>
    <p>Приложение работает в офлайн-режиме. Ранее просмотренные страницы сохранены.</p>
    <a href="/daily-summary">Перейти на главную</a>
  </div>
</body>
</html>`,
    { status: 200, headers: { 'Content-Type': 'text/html; charset=utf-8' } },
  );
}

// ── Update messages from clients ─────────────────────────────────────────────
self.addEventListener('message', (event) => {
  if (event.data === 'SKIP_WAITING') {
    self.skipWaiting();
  }
});
