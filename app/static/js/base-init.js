/**
 * Script d'initialisation de base pour l'application.
 * Configure les URLs, le service worker et gère le centre de notifications broadcast.
 */
(function() {
    'use strict';

    window.APP_URLS = window.APP_URLS || {};
    if (window.APP_SERVER_TIME_URL) {
        window.APP_URLS.server_time = window.APP_SERVER_TIME_URL;
    }

    if ('serviceWorker' in navigator) {
        navigator.serviceWorker.register('/service-worker.js', { scope: '/' })
            .then(function(registration) {
                console.log('Service Worker enregistré:', registration.scope);
                if (registration.installing) {
                    registration.installing.addEventListener('statechange', function() {
                        if (this.state === 'activated') {
                            console.log('Service Worker activé');
                        }
                    });
                }
            })
            .catch(function(error) {
                console.error('Erreur enregistrement Service Worker:', error);
            });
    }

    // ── Notifications broadcast ───────────────────────────────────────────────
    var STORAGE_KEY = 'seen_broadcasts';

    function getSeenIds() {
        try { return JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]'); } catch(e) { return []; }
    }

    function markSeen(id) {
        var seen = getSeenIds();
        var sid  = String(id);
        if (seen.indexOf(sid) === -1) {
            seen.push(sid);
            if (seen.length > 200) seen = seen.slice(seen.length - 200);
            localStorage.setItem(STORAGE_KEY, JSON.stringify(seen));
        }
        // Sync serveur (best-effort, silencieux)
        var csrf = window.CSRF_TOKEN || '';
        if (csrf) {
            fetch('/notifications/read', {
                method: 'POST',
                credentials: 'same-origin',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrf,
                    'X-Requested-With': 'XMLHttpRequest'
                },
                body: JSON.stringify({ ids: [parseInt(id, 10) || id] })
            }).catch(function() {});
        }
    }

    /**
     * Masque les <li data-notif-id> déjà lus et les séparateurs de date
     * si tous les items de ce groupe sont lus.
     */
    function refreshBell() {
        var list   = document.getElementById('notif-list');
        var seen   = getSeenIds();
        var count  = 0;

        if (list) {
            var children = Array.from(list.children);
            var currentSeparator = null;
            var groupHasVisible  = false;

            children.forEach(function(el) {
                if (el.classList.contains('notif-separator')) {
                    // Masquer le séparateur précédent si son groupe était vide
                    if (currentSeparator && !groupHasVisible) {
                        currentSeparator.style.display = 'none';
                    }
                    currentSeparator = el;
                    groupHasVisible  = false;
                    // Afficher par défaut; on le masquera après si besoin
                    el.style.display = '';
                } else {
                    var id     = String(el.dataset.notifId || '');
                    var isSeen = id && seen.indexOf(id) !== -1;
                    el.style.display = isSeen ? 'none' : '';
                    if (!isSeen) {
                        count++;
                        groupHasVisible = true;
                    }
                }
            });
            // Traiter le dernier groupe
            if (currentSeparator && !groupHasVisible) {
                currentSeparator.style.display = 'none';
            }
        }

        // Badge
        var badge = document.getElementById('notif-bell-badge');
        if (badge) {
            badge.textContent = count > 99 ? '99+' : String(count);
            badge.classList.toggle('hidden', count === 0);
            badge.style.display = count > 0 ? 'inline-flex' : 'none';
        }

        // État vide
        var empty = document.getElementById('notif-empty');
        if (empty) {
            empty.classList.toggle('hidden', count > 0);
        }
    }

    function setBellPanelOpen(open) {
        var panel = document.getElementById('notif-bell-panel');
        if (!panel) return;
        if (open) {
            panel.classList.remove('invisible', 'opacity-0', 'scale-95');
            panel.classList.add('opacity-100', 'scale-100');
        } else {
            panel.classList.add('invisible', 'opacity-0', 'scale-95');
            panel.classList.remove('opacity-100', 'scale-100');
        }
    }

    function initNotifBell() {
        var bellBtn    = document.getElementById('notif-bell-btn');
        var panel      = document.getElementById('notif-bell-panel');
        var markAllBtn = document.getElementById('notif-mark-all');
        if (!bellBtn || !panel) return;

        refreshBell();

        bellBtn.addEventListener('click', function(e) {
            e.stopPropagation();
            var isOpen = !panel.classList.contains('invisible');
            var profileMenu = document.querySelector('[data-profile-menu]');
            if (profileMenu && !profileMenu.classList.contains('invisible')) {
                profileMenu.classList.add('invisible', 'opacity-0', 'scale-95');
                profileMenu.classList.remove('opacity-100', 'scale-100');
            }
            setBellPanelOpen(!isOpen);
        });

        document.addEventListener('click', function(e) {
            var wrap = document.getElementById('notif-bell-wrap');
            if (wrap && !wrap.contains(e.target)) {
                setBellPanelOpen(false);
            }
        });

        if (markAllBtn) {
            markAllBtn.addEventListener('click', function() {
                var items = document.querySelectorAll('#notif-list [data-notif-id]');
                var ids = [];
                items.forEach(function(li) {
                    markSeen(li.dataset.notifId);
                    ids.push(li.dataset.notifId);
                });
                refreshBell();
                setBellPanelOpen(false);
                // Toast confirmation
                if (typeof window.createToast === 'function' && ids.length > 0) {
                    window.createToast('success', 'Toutes les notifications ont été marquées comme lues.');
                }
            });
        }

        panel.addEventListener('click', function(e) {
            var btn = e.target.closest('.notif-item-read');
            if (!btn) return;
            var id = btn.dataset.id;
            if (id) {
                markSeen(id);
                refreshBell();
            }
        });
    }

    // ── API publique ──────────────────────────────────────────────────────────
    window.BroadcastCenter = {
        markSeen: markSeen,
        markAllSeen: function() {
            var items = document.querySelectorAll('#notif-list [data-notif-id]');
            items.forEach(function(li) { markSeen(li.dataset.notifId); });
            refreshBell();
        },
        getUnseenCount: function() {
            var items = document.querySelectorAll('#notif-list [data-notif-id]');
            var seen  = getSeenIds();
            var count = 0;
            items.forEach(function(li) { if (seen.indexOf(String(li.dataset.notifId)) === -1) count++; });
            return count;
        },
        refresh: refreshBell
    };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initNotifBell);
    } else {
        initNotifBell();
    }
})();
