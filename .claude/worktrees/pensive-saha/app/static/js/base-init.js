/**
 * Script d'initialisation de base pour l'application.
 * Configure les URLs, le service worker et affiche les notifications broadcast.
 */
(function() {
    'use strict';

    // Pass server URLs to window object for external scripts
    window.APP_URLS = window.APP_URLS || {};
    if (window.APP_SERVER_TIME_URL) {
        window.APP_URLS.server_time = window.APP_SERVER_TIME_URL;
    }

    // Enregistrer le service worker IMMÉDIATEMENT pour iOS Safari
    if ('serviceWorker' in navigator) {
        navigator.serviceWorker.register('/service-worker.js', { scope: '/' })
            .then(function(registration) {
                console.log('Service Worker enregistré:', registration.scope);
                if (registration.installing) {
                    registration.installing.addEventListener('statechange', function() {
                        if (this.state === 'activated') {
                            console.log('Service Worker activé - contrôle de la page');
                        }
                    });
                }
            })
            .catch(function(error) {
                console.error('Erreur enregistrement Service Worker:', error);
            });
    }

    // ── Notifications broadcast globales — affichage modal ───────────────────
    var STORAGE_KEY = 'seen_broadcasts';

    // Styles inline pour éviter les problèmes avec le CSS compilé statique
    var levelStyles = {
        info:    { iconBg: '#e0f2fe', iconColor: '#0284c7', badgeColor: '#0284c7', btnBg: '#0ea5e9', btnHoverBg: '#38bdf8' },
        warning: { iconBg: '#fef3c7', iconColor: '#d97706', badgeColor: '#d97706', btnBg: '#f59e0b', btnHoverBg: '#fbbf24' },
        error:   { iconBg: '#fee2e2', iconColor: '#dc2626', badgeColor: '#dc2626', btnBg: '#ef4444', btnHoverBg: '#f87171' },
    };

    function getSeenIds() {
        try { return JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]'); } catch(e) { return []; }
    }

    function markSeen(id) {
        var seen = getSeenIds();
        if (seen.indexOf(id) === -1) {
            seen.push(id);
            if (seen.length > 200) seen = seen.slice(seen.length - 200);
            localStorage.setItem(STORAGE_KEY, JSON.stringify(seen));
        }
    }

    function showBroadcastModal(queue) {
        if (!queue || !queue.length) return;
        var n = queue.shift();

        var modal     = document.getElementById('broadcast-modal');
        var icon      = document.getElementById('broadcast-modal-icon');
        var badge     = document.getElementById('broadcast-modal-badge');
        var titleEl   = document.getElementById('broadcast-modal-title');
        var msgEl     = document.getElementById('broadcast-modal-message');
        var acceptBtn = document.getElementById('broadcast-modal-accept');
        var card      = document.getElementById('broadcast-modal-card');
        if (!modal || !acceptBtn) return;

        var style = levelStyles[n.level] || levelStyles.info;

        // Appliquer les styles inline (robuste contre le CSS compilé statique)
        if (icon) {
            icon.style.backgroundColor = style.iconBg;
            icon.style.color = style.iconColor;
        }
        if (badge) {
            badge.style.color = style.badgeColor;
        }
        acceptBtn.style.backgroundColor = style.btnBg;
        acceptBtn.style.color = '#ffffff';
        acceptBtn.onmouseenter = function() { this.style.backgroundColor = style.btnHoverBg; };
        acceptBtn.onmouseleave = function() { this.style.backgroundColor = style.btnBg; };

        if (titleEl) titleEl.textContent = n.title || 'Notification';
        if (msgEl)   msgEl.textContent   = n.message || '';

        // Afficher le modal
        modal.style.display = '';
        modal.classList.remove('hidden');

        // Flouter le header
        var header = document.querySelector('[data-app-header]');
        if (header) {
            header.style.transition = 'filter 0.25s ease';
            header.style.filter = 'blur(4px)';
            header.style.pointerEvents = 'none';
        }

        // Animer l'entrée
        if (card) {
            card.style.opacity = '0';
            card.style.transform = 'scale(0.92)';
            card.style.transition = 'opacity 0.25s ease, transform 0.25s ease';
            requestAnimationFrame(function() {
                requestAnimationFrame(function() {
                    card.style.opacity = '1';
                    card.style.transform = 'scale(1)';
                });
            });
        }

        function closeModal() {
            // Retirer le flou du header
            if (header) {
                header.style.filter = '';
                header.style.pointerEvents = '';
            }
            if (card) {
                card.style.opacity = '0';
                card.style.transform = 'scale(0.92)';
            }
            setTimeout(function() {
                modal.classList.add('hidden');
                if (queue.length) {
                    setTimeout(function() { showBroadcastModal(queue); }, 150);
                }
            }, 200);
        }

        // Bouton Accepter
        acceptBtn.onclick = function() {
            markSeen(n.id);
            closeModal();
        };
    }

    function processBroadcasts(broadcasts) {
        if (!broadcasts || !broadcasts.length) return;
        var seen = getSeenIds();
        var unseen = broadcasts.filter(function(n) {
            // Comparer en string pour éviter les problèmes int/string
            return seen.indexOf(n.id) === -1 && seen.indexOf(String(n.id)) === -1;
        });
        if (!unseen.length) return;
        showBroadcastModal(unseen.slice());
    }

    function initBroadcasts() {
        // Priorité 1 : Appel API fresh (ignore le cache du service worker)
        fetch('/api/notifications/broadcasts', {
            credentials: 'same-origin',
            cache: 'no-store',
            headers: { 'X-Requested-With': 'XMLHttpRequest' }
        })
        .then(function(r) {
            if (!r.ok) throw new Error('HTTP ' + r.status);
            return r.json();
        })
        .then(function(data) {
            processBroadcasts(data);
        })
        .catch(function() {
            // Priorité 2 : Fallback sur les données serveur dans la page
            processBroadcasts(window.BROADCAST_NOTIFICATIONS || []);
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initBroadcasts);
    } else {
        initBroadcasts();
    }
})();

