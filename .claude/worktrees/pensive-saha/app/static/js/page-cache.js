/**
 * Gestion du cache des pages pour le service worker.
 */
(function() {
    'use strict';
    
    // Mettre en cache la page actuelle pour le mode offline
    if ('serviceWorker' in navigator && navigator.serviceWorker.controller) {
        const currentUrl = window.location.href;
        navigator.serviceWorker.controller.postMessage({
            type: 'CACHE_PAGE',
            url: currentUrl
        });
    }

    // Mettre en cache les pages visitées lors de la navigation
    document.querySelectorAll('a[href]').forEach((anchor) => {
        anchor.addEventListener('click', (event) => {
            const href = anchor.getAttribute('href') || '';
            if (anchor.target === '_blank' || anchor.hasAttribute('download')) return;
            if (href.startsWith('#') || href.startsWith('javascript:')) return;
            if (href.startsWith('/static/') || href.startsWith('/api/')) return;
            
            // Mettre en cache la page de destination avant la navigation
            if ('serviceWorker' in navigator && navigator.serviceWorker.controller) {
                const targetUrl = href.startsWith('http') ? href : window.location.origin + href;
                navigator.serviceWorker.controller.postMessage({
                    type: 'CACHE_PAGE',
                    url: targetUrl
                });
            }
        });
    });
})();

