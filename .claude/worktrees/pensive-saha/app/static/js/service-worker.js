const STATIC_CACHE = 'templateapp-static-v8';
const DYNAMIC_CACHE = 'templateapp-dynamic-v8';

// Ressources à mettre en cache immédiatement
const STATIC_ASSETS = [
  '/',
  '/auth/login',
  '/manifest.json',
  '/offline.html',
  '/static/css/main.css',
  '/static/js/main.js',
  '/static/js/pwa.js',
  '/static/js/filters.js',
  '/static/js/service-worker.js',
  '/static/img/logo.png',
];

// Fonction pour déterminer si une requête est une page HTML
function isHTMLRequest(request) {
  const acceptHeader = request.headers.get('accept');
  return acceptHeader && acceptHeader.includes('text/html');
}

// Fonction pour déterminer si une URL est une page HTML (pas une ressource statique)
function isHTMLPage(url) {
  const pathname = url.pathname;
  // Exclure les fichiers statiques, les API, et les autres ressources
  return !pathname.startsWith('/static/') &&
         !pathname.startsWith('/api/') &&
         !pathname.startsWith('/notifications/') &&
         !pathname.startsWith('/icon/') &&
         !pathname.includes('.') || 
         pathname.endsWith('/') ||
         pathname === '/';
}

// Installation : mettre en cache les ressources statiques
self.addEventListener('install', (event) => {
  console.log('[Service Worker] Installation en cours...');
  event.waitUntil(
    caches.open(STATIC_CACHE).then((cache) => {
      console.log('[Service Worker] Mise en cache des ressources statiques');
      return Promise.allSettled(
        STATIC_ASSETS.map((url) => 
          cache.add(url).catch((err) => {
            console.warn(`[Service Worker] Échec du cache pour ${url}:`, err);
          })
        )
      );
    })
  );
  // Forcer l'activation immédiate
  self.skipWaiting();
});

// Activation : nettoyer les anciens caches et prendre le contrôle
self.addEventListener('activate', (event) => {
  console.log('[Service Worker] Activation en cours...');
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys
          .filter((key) => key !== STATIC_CACHE && key !== DYNAMIC_CACHE)
          .map((key) => {
            console.log(`[Service Worker] Suppression de l'ancien cache: ${key}`);
            return caches.delete(key);
          })
      );
    }).then(() => {
      // Prendre le contrôle de toutes les pages ouvertes immédiatement
      return self.clients.claim();
    })
  );
  console.log('[Service Worker] Activé et contrôle la page');
});

// Écouter les messages du client pour mettre en cache les pages visitées
self.addEventListener('message', (event) => {
  if (event.data && event.data.type === 'CACHE_PAGE') {
    const url = event.data.url;
    if (url) {
      fetch(url)
        .then((response) => {
          if (response.status === 200) {
            const clone = response.clone();
            caches.open(DYNAMIC_CACHE).then((cache) => {
              cache.put(url, clone).then(() => {
                console.log(`[Service Worker] Page mise en cache via message: ${url}`);
              });
            });
          }
        })
        .catch((error) => {
          console.warn(`[Service Worker] Erreur mise en cache via message: ${url}`, error);
        });
    }
  }
});

// Stratégie de cache : Network First avec fallback Cache pour les pages HTML, Cache First pour les ressources statiques
self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // Ignorer les requêtes non-GET
  if (request.method !== 'GET') {
    return;
  }

  // Ignorer les requêtes vers d'autres domaines
  if (url.origin !== location.origin) {
    return;
  }

  const isHTML = isHTMLRequest(request) && isHTMLPage(url);
  const isStatic = url.pathname.startsWith('/static/');

  // TOUJOURS répondre pour éviter le message d'erreur Safari
  event.respondWith(
    (async () => {
      try {
        // Pour les ressources statiques : Cache First
        if (isStatic) {
          const cached = await caches.match(request);
          if (cached) {
            console.log(`[Service Worker] Cache hit (statique): ${url.pathname}`);
            // Mettre à jour en arrière-plan si en ligne
            if (navigator.onLine) {
              fetch(request).then((response) => {
                if (response.status === 200) {
                  caches.open(STATIC_CACHE).then((cache) => {
                    cache.put(request, response.clone()).catch(() => {});
                  });
                }
              }).catch(() => {});
            }
            return cached;
          }
          
          // Si pas en cache, essayer le réseau
          try {
            const response = await fetch(request);
            if (response.status === 200) {
              const clone = response.clone();
              caches.open(STATIC_CACHE).then((cache) => {
                cache.put(request, clone).catch(() => {});
              });
            }
            return response;
          } catch (error) {
            console.log(`[Service Worker] Erreur réseau pour ressource statique: ${url.pathname}`);
            return new Response('Ressource non disponible hors ligne', { 
              status: 503,
              headers: { 'Content-Type': 'text/plain' }
            });
          }
        }

        // Pour les pages HTML : Cache First avec mise à jour en arrière-plan
        // Cela évite le message d'erreur du navigateur en répondant immédiatement depuis le cache
        if (isHTML) {
          // 1. CHERCHER D'ABORD DANS LE CACHE (réponse immédiate)
          const urlVariants = [
            request.url,
            url.pathname,
            url.pathname + '/',
            url.pathname.replace(/\/$/, ''),
          ];
          
          // Chercher dans le cache avec toutes les variantes
          for (const variant of urlVariants) {
            const cached = await caches.match(variant);
            if (cached) {
              console.log(`[Service Worker] Cache hit IMMÉDIAT (page HTML): ${variant}`);
              
              // Mettre à jour en arrière-plan si en ligne (non bloquant)
              if (navigator.onLine) {
                fetch(request, { cache: 'no-cache' })
                  .then((response) => {
                    if (response.status === 200) {
                      const clone = response.clone();
                      caches.open(DYNAMIC_CACHE).then((cache) => {
                        cache.put(request, clone).catch(() => {});
                      });
                      console.log(`[Service Worker] Page mise à jour en arrière-plan: ${url.pathname}`);
                    }
                  })
                  .catch(() => {
                    // Ignorer les erreurs de mise à jour en arrière-plan
                  });
              }
              
              // Retourner immédiatement depuis le cache
              return cached;
            }
          }
          
          // 2. SI PAS DANS LE CACHE, ESSAYER LE RÉSEAU (avec timeout très court)
          if (navigator.onLine) {
            try {
              const controller = new AbortController();
              const timeoutId = setTimeout(() => controller.abort(), 500); // 500ms max pour éviter l'erreur navigateur
              
              const response = await fetch(request, { 
                signal: controller.signal,
                cache: 'no-cache'
              });
              clearTimeout(timeoutId);
              
              // Si succès, mettre en cache ET retourner la réponse
              if (response.status === 200) {
                const clone = response.clone();
                caches.open(DYNAMIC_CACHE).then((cache) => {
                  cache.put(request, clone).catch(() => {});
                });
                console.log(`[Service Worker] Page chargée depuis réseau et mise en cache: ${url.pathname}`);
                return response;
              }
            } catch (error) {
              // Erreur réseau ou timeout : continuer vers les fallbacks
              console.log(`[Service Worker] Erreur réseau pour ${url.pathname}, utilisation fallback...`);
            }
          }
          
          // 3. SI PAS DE CACHE ET PAS DE RÉSEAU, ESSAYER DES PAGES DE FALLBACK
          const fallbackPages = ['/offline.html', '/auth/login', '/'];
          for (const fallback of fallbackPages) {
            const cached = await caches.match(fallback);
            if (cached) {
              console.log(`[Service Worker] Fallback trouvé: ${fallback}`);
              return cached;
            }
          }
          
          // 4. DERNIER RECOURS : page HTML minimale
          console.log('[Service Worker] Aucun cache trouvé, retour page minimale');
          return new Response(
            '<!DOCTYPE html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover"><title>Hors ligne - TemplateApp</title><style>body{font-family:system-ui,-apple-system,sans-serif;padding:2rem;text-align:center;background:#f1f5f9;color:#1e293b;min-height:100vh;display:flex;flex-direction:column;justify-content:center;align-items:center}h1{color:#0f172a;margin-bottom:1rem;font-size:1.5rem}p{color:#64748b;margin-bottom:2rem;max-width:400px}button{background:#14b8a6;color:white;border:none;padding:0.75rem 1.5rem;border-radius:0.5rem;font-size:1rem;cursor:pointer;transition:background 0.2s}button:hover{background:#0d9488}button:active{transform:scale(0.98)}</style></head><body><h1>Mode hors ligne</h1><p>Vous n\'êtes pas connecté à Internet. Cette page n\'est pas disponible hors ligne.</p><button onclick="window.location.reload()">Réessayer</button></body></html>',
            { 
              headers: { 
                'Content-Type': 'text/html; charset=utf-8',
                'Cache-Control': 'no-cache'
              } 
            }
          );
        }

        // Pour les autres ressources (API, etc.) : Cache First
        const cached = await caches.match(request);
        if (cached) {
          console.log(`[Service Worker] Cache hit: ${url.pathname}`);
          return cached;
        }

        // Essayer le réseau
        try {
          const response = await fetch(request);
          // Mettre en cache si succès
          if (response.status === 200) {
            const clone = response.clone();
            const cacheName = isStatic ? STATIC_CACHE : DYNAMIC_CACHE;
            caches.open(cacheName).then((cache) => {
              cache.put(request, clone).catch(() => {});
            });
          }
          return response;
        } catch (error) {
          // Pour les API, retourner une erreur JSON
          if (url.pathname.startsWith('/api/') || url.pathname.startsWith('/notifications/')) {
            return new Response(
              JSON.stringify({ error: 'Mode hors ligne', offline: true }),
              {
                status: 503,
                headers: { 'Content-Type': 'application/json' }
              }
            );
          }
          
          // Pour les images, retourner une réponse vide
          if (request.headers.get('accept') && request.headers.get('accept').includes('image')) {
            return new Response('', { status: 404 });
          }
          
          // Pour les autres ressources, retourner une erreur
          return new Response('Ressource non disponible hors ligne', { 
            status: 503,
            headers: { 'Content-Type': 'text/plain' }
          });
        }
      } catch (error) {
        // En cas d'erreur inattendue, retourner une réponse minimale
        console.error('[Service Worker] Erreur inattendue:', error);
        return new Response('Erreur de chargement', { 
          status: 500,
          headers: { 'Content-Type': 'text/plain' }
        });
      }
    })()
  );
});

