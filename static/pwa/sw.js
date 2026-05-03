const CACHE_NAME = 'genomeai-pwa-static-v1';
const CORE_ASSETS = [
  '/static/pwa/manifest.webmanifest',
  '/static/pwa/icon-any.svg',
  '/static/pwa/icon-maskable.svg'
];
self.addEventListener('install', (event) => {
  event.waitUntil(caches.open(CACHE_NAME).then((cache) => cache.addAll(CORE_ASSETS)).catch(() => null));
  self.skipWaiting();
});
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key))))
  );
  self.clients.claim();
});
self.addEventListener('fetch', (event) => {
  const request = event.request;
  if (request.method !== 'GET') return;
  const url = new URL(request.url);
  if (!url.pathname.startsWith('/static/pwa/')) return;
  event.respondWith(caches.match(request).then((cached) => cached || fetch(request)));
});
