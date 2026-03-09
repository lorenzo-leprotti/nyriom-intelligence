/**
 * Service Worker for Nyriom Intelligence PWA
 * Handles caching strategies, offline functionality, and forced updates
 */

const CACHE_VERSION = 'nyriom-intel-v5';
const OFFLINE_URL = '/offline';

const PRECACHE_ASSETS = [
  '/',
  '/offline',
  '/static/icons/icon-192.png',
  '/static/icons/icon-512.png',
  '/static/manifest.json'
];

self.addEventListener('install', (event) => {
  console.log('[Service Worker] Installing...');
  event.waitUntil(
    caches.open(CACHE_VERSION)
      .then((cache) => cache.addAll(PRECACHE_ASSETS))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  console.log('[Service Worker] Activating...');
  event.waitUntil(
    caches.keys()
      .then((cacheNames) => Promise.all(
        cacheNames.map((cacheName) => {
          if (cacheName !== CACHE_VERSION) {
            return caches.delete(cacheName);
          }
        })
      ))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('message', (event) => {
  if (event.data && event.data.type === 'FORCE_UPDATE') {
    event.waitUntil(
      caches.keys().then((cacheNames) =>
        Promise.all(cacheNames.map((c) => caches.delete(c)))
      ).then(() => {
        self.clients.matchAll().then((clients) => {
          clients.forEach((client) => client.postMessage({ type: 'CACHE_CLEARED' }));
        });
      })
    );
  }
});

self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);
  if (request.method !== 'GET') return;
  if (url.origin !== self.location.origin) return;
  if (url.pathname.startsWith('/api/')) return;

  if (isStaticAsset(url.pathname)) {
    event.respondWith(cacheFirst(request));
    return;
  }
  event.respondWith(networkFirst(request));
});

async function cacheFirst(request) {
  const cache = await caches.open(CACHE_VERSION);
  const cached = await cache.match(request);
  if (cached) return cached;
  try {
    const response = await fetch(request);
    if (response.status === 200) cache.put(request, response.clone());
    return response;
  } catch (error) {
    throw error;
  }
}

async function networkFirst(request) {
  const cache = await caches.open(CACHE_VERSION);
  try {
    const response = await fetch(request);
    if (response.status === 200) cache.put(request, response.clone());
    return response;
  } catch (error) {
    const cached = await cache.match(request);
    if (cached) return cached;
    if (isHTMLPage(new URL(request.url).pathname)) {
      const offlineResponse = await cache.match(OFFLINE_URL);
      if (offlineResponse) return offlineResponse;
    }
    throw error;
  }
}

function isStaticAsset(pathname) {
  return ['.css', '.js', '.png', '.jpg', '.svg', '.gif', '.woff', '.woff2'].some(ext => pathname.endsWith(ext)) || pathname.includes('/static/');
}

function isHTMLPage(pathname) {
  return pathname === '/' || pathname.startsWith('/dashboard') || pathname.startsWith('/events') ||
         pathname.startsWith('/archive') || pathname === '/offline' ||
         (!pathname.includes('.') && !pathname.startsWith('/api/'));
}
