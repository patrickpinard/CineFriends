// Afficher le spinner immédiatement au chargement
document.documentElement.classList.add('is-loading');

// S'assurer que le spinner est visible dès le début
(function() {
    const skeleton = document.getElementById('page-skeleton');
    if (skeleton) {
        skeleton.removeAttribute('aria-hidden');
    }
})();

document.addEventListener('DOMContentLoaded', function () {
    const skeleton = document.getElementById('page-skeleton');
    const startTime = Date.now();
    const minDisplayTime = 500; // Minimum 500ms pour que le spinner soit visible
    
    function hideSpinner() {
        const elapsed = Date.now() - startTime;
        const remaining = Math.max(0, minDisplayTime - elapsed);
        
        setTimeout(() => {
            document.documentElement.classList.remove('is-loading');
            if (skeleton) {
                skeleton.setAttribute('aria-hidden', 'true');
            }
        }, remaining);
    }
    
    // Attendre que la page soit complètement chargée
    if (document.readyState === 'complete') {
        hideSpinner();
    } else {
        window.addEventListener('load', hideSpinner);
        // Fallback : masquer après 3 secondes maximum même si la page n'est pas complètement chargée
        setTimeout(hideSpinner, 3000);
    }

    // Mise à jour de l'heure locale du Raspberry Pi
    const timeElement = document.getElementById('header-time');
    let serverTimeBase = null; // Timestamp de base du serveur
    let serverTimeClientBase = null; // Timestamp client au moment de la synchronisation
    
    function updateTime() {
        if (!timeElement || !serverTimeBase || !serverTimeClientBase) return;
        
        // Calculer l'heure actuelle du serveur en ajoutant l'écart de temps écoulé
        const now = Date.now();
        const elapsed = now - serverTimeClientBase;
        const serverTimeNow = new Date(serverTimeBase.getTime() + elapsed);
        
        const hours = String(serverTimeNow.getHours()).padStart(2, '0');
        const minutes = String(serverTimeNow.getMinutes()).padStart(2, '0');
        const seconds = String(serverTimeNow.getSeconds()).padStart(2, '0');
        const timeString = `${hours}:${minutes}:${seconds}`;
        timeElement.textContent = timeString;
        timeElement.setAttribute('datetime', serverTimeNow.toISOString());
    }
    
    // Synchroniser avec l'heure locale du serveur (Raspberry Pi)
    function syncServerTime() {
        // Note: CSRF_TOKEN is defined in the template, but we might need to handle it if this script is external.
        // For now, this fetch is a GET request so CSRF token is not strictly required in headers unless the endpoint enforces it.
        // The original code used {{ url_for(...) }} which we can't use in a static JS file.
        // We will need to pass the URL or use a relative path.
        // Assuming /api/server-time or similar. Let's check the route.
        // The original code was: fetch('{{ url_for("main.server_time") }}', ...
        
        // We will use a relative path assuming the app structure.
        // Or better, we can keep the URL definition in a small inline script block in base.html and use a global variable.
        
        const serverTimeUrl = window.APP_URLS ? window.APP_URLS.server_time : '/api/server-time'; // Fallback

        fetch(serverTimeUrl, {
            headers: { 'Accept': 'application/json' },
            credentials: 'same-origin',
        })
        .then(response => response.json())
        .then(data => {
            serverTimeBase = new Date(data.timestamp);
            serverTimeClientBase = Date.now();
            updateTime();
        })
        .catch((error) => {
            console.warn('Erreur synchronisation heure serveur:', error);
            serverTimeBase = new Date();
            serverTimeClientBase = Date.now();
            updateTime();
        });
    }
    
    // Initial sync
    syncServerTime();
    
    // Update every second
    setInterval(updateTime, 1000);
    
    // Re-sync every 5 minutes
    setInterval(syncServerTime, 5 * 60 * 1000);

    // --- UI Logic (Notifications, Sidebar, Modals) ---
    
    const sidebarToggle = document.querySelector('[data-sidebar-toggle]');
    const body = document.body;
    const SIDEBAR_STORAGE_KEY = 'sidebar_collapsed';
    
    const notificationToggle = document.querySelector('[data-notification-toggle]');
    const notificationMenu = document.querySelector('[data-notification-menu]');
    const notificationList = document.querySelector('[data-notification-list]');
    const notificationMarkAllBtn = document.querySelector('[data-notification-mark-all]');
    const notificationEmptyTemplate = document.getElementById('notification-empty-template');
    
    const profileToggle = document.querySelector('[data-profile-toggle]');
    const profileMenu = document.querySelector('[data-profile-menu]');
    
    const mobileToggle = document.querySelector('[data-mobile-nav-toggle]');
    const mobileNav = document.querySelector('[data-mobile-nav]');
    const mobileBackdrop = document.querySelector('[data-mobile-nav-backdrop]');
    const mobileClose = document.querySelector('[data-mobile-nav-close]');
    
    const confirmModal = document.getElementById('confirm-modal');
    const confirmMessageEl = confirmModal?.querySelector('[data-confirm-message]');
    const confirmCancelBtn = confirmModal?.querySelectorAll('[data-confirm-cancel]');
    const confirmApproveBtn = confirmModal?.querySelector('[data-confirm-approve]');
    let pendingConfirmForm = null;

    const showLoadingOverlay = () => {
        document.documentElement.classList.add('is-loading');
        const skeleton = document.getElementById('page-skeleton');
        if (skeleton) {
            skeleton.removeAttribute('aria-hidden');
        }
    };

    // Flash messages - utiliser la fonction createToast définie dans base.html
    function displayFlashMessages() {
    const flashDataScript = document.getElementById('flash-data');
        if (!flashDataScript) return;

        try {
            const messages = JSON.parse(flashDataScript.textContent);
            messages.forEach(([category, message]) => {
                // Attendre un peu pour que createToast soit disponible, puis utiliser le fallback si nécessaire
                const showToast = () => {
                    if (typeof window.createToast === 'function') {
                        window.createToast(category, message);
                    } else {
                        // Fallback: créer le toast directement
                        const toastContainer = document.getElementById('toast-container');
                        if (!toastContainer || !message) return;

                        const toastVariants = {
                            success: { title: 'Succès', indicator: 'bg-emerald-500', accent: 'text-emerald-600', bg: 'bg-white', text: 'text-slate-700', border: 'border-slate-200' },
                            warning: { title: 'Attention', indicator: 'bg-white', accent: 'text-white', bg: 'bg-red-600', text: 'text-white', border: 'border-red-700' },
                            danger: { title: 'Erreur', indicator: 'bg-rose-500', accent: 'text-rose-600', bg: 'bg-white', text: 'text-slate-700', border: 'border-slate-200' },
                            info: { title: 'Information', indicator: 'bg-sky-500', accent: 'text-sky-600', bg: 'bg-white', text: 'text-slate-700', border: 'border-slate-200' },
                            default: { title: 'Notification', indicator: 'bg-slate-400', accent: 'text-slate-600', bg: 'bg-white', text: 'text-slate-700', border: 'border-slate-200' },
                        };

                        const variant = toastVariants[category] || toastVariants.default;
                        const isWarning = category === 'warning';
                        const toast = document.createElement('div');
                        toast.className = `pointer-events-auto overflow-hidden rounded-2xl border ${variant.border} ${variant.bg} shadow-lg ring-1 ring-black/5 transition duration-200 ease-out`;
                        toast.style.opacity = '0';
                        toast.style.transform = 'translateY(-12px)';
                        
                        // Pour les warnings, ajouter un style pour les positionner plus bas
                        if (isWarning) {
                            toast.style.marginTop = '4rem';
                        }

                        const inner = document.createElement('div');
                        inner.className = `flex items-start gap-3 p-4 text-sm ${variant.text}`;

                        const dot = document.createElement('span');
                        dot.className = `mt-1.5 h-2.5 w-2.5 rounded-full ${variant.indicator}`;
                        inner.appendChild(dot);

                        const content = document.createElement('div');
                        content.className = 'flex-1';

                        const titleEl = document.createElement('p');
                        titleEl.className = `font-semibold text-base ${variant.accent}`;
                        titleEl.textContent = variant.title;
                        
                        content.appendChild(titleEl);
                        
                        const messageEl = document.createElement('p');
                        messageEl.className = `mt-0.5 ${variant.text}`;
                        messageEl.textContent = message;
                        content.appendChild(messageEl);
                        
                        inner.appendChild(content);
                        toast.appendChild(inner);
                        toastContainer.appendChild(toast);
                        
                        requestAnimationFrame(() => {
                            toast.style.opacity = '1';
                            toast.style.transform = 'translateY(0)';
                        });
                        
                        // Afficher pendant 5 secondes pour tous les messages
                        const displayTime = 5000;
                        setTimeout(() => {
                            toast.style.opacity = '0';
                            toast.style.transform = 'translateY(-12px)';
                            setTimeout(() => toast.remove(), 200);
                        }, displayTime);
                    }
                };

                // Essayer immédiatement, sinon attendre un peu
                if (typeof window.createToast === 'function') {
                    showToast();
                } else {
                    // Attendre que le DOM soit complètement chargé
                    setTimeout(showToast, 100);
                }
            });
        } catch (e) {
            console.error('Error parsing flash messages', e);
        }
    }

    // Attendre que le DOM soit prêt
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', displayFlashMessages);
    } else {
        // DOM déjà chargé, exécuter immédiatement ou après un court délai
        setTimeout(displayFlashMessages, 50);
    }

    function applySidebarState(collapsed) {
        body.classList.toggle('sidebar-collapsed', collapsed);
        sidebarToggle?.setAttribute('aria-pressed', collapsed ? 'true' : 'false');
    }

    function markNotificationsAsRead(ids) {
        // Use CSRF_TOKEN from global scope (defined in base.html)
        const payload = ids && ids.length ? { ids } : {};
        fetch(window.APP_URLS.notifications_mark_read || '/notifications/mark-read', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': window.CSRF_TOKEN,
            },
            body: JSON.stringify(payload),
        }).catch(() => {
            console.warn('Impossible de mettre à jour les notifications.');
        });
    }

    const storedSidebarState = localStorage.getItem(SIDEBAR_STORAGE_KEY);
    if (storedSidebarState !== null) {
        applySidebarState(storedSidebarState === 'true');
    }

    sidebarToggle?.addEventListener('click', () => {
        const collapsed = !body.classList.contains('sidebar-collapsed');
        applySidebarState(collapsed);
        localStorage.setItem(SIDEBAR_STORAGE_KEY, String(collapsed));
    });

    const updateNotificationBadge = () => {
        if (!notificationToggle) return;
        const badge = notificationToggle.querySelector('[data-notification-badge]');
        const unreadCount = notificationMenu?.querySelectorAll('[data-unread="true"]').length || 0;
        const totalCount = notificationMenu?.querySelectorAll('[data-notification-id]').length || 0;
        if (notificationMarkAllBtn) {
            notificationMarkAllBtn.disabled = totalCount === 0;
        }
        if (badge && unreadCount <= 0) {
            badge.remove();
        } else if (badge) {
            badge.textContent = String(unreadCount);
        } else if (unreadCount > 0) {
            const newBadge = document.createElement('span');
            newBadge.dataset.notificationBadge = 'true';
            newBadge.className = 'absolute -top-1 -right-1 inline-flex h-4 min-w-[16px] items-center justify-center rounded-full bg-rose-500 px-1 text-[10px] font-semibold text-white';
            newBadge.textContent = String(unreadCount);
            notificationToggle.appendChild(newBadge);
        }
    };

    if (notificationToggle && notificationMenu) {
        const toggleNotifications = () => {
            const isOpen = notificationMenu.classList.contains('opacity-100');
            notificationMenu.classList.toggle('opacity-100', !isOpen);
            notificationMenu.classList.toggle('opacity-0', isOpen);
            notificationMenu.classList.toggle('invisible', isOpen);
            notificationMenu.classList.toggle('scale-100', !isOpen);
            notificationMenu.classList.toggle('scale-95', isOpen);
            if (!isOpen) {
                const unreadItems = notificationMenu.querySelectorAll('[data-unread="true"]');
                if (unreadItems.length) {
                    const ids = Array.from(unreadItems).map((el) => {
                        el.setAttribute('data-unread', 'false');
                        el.classList.remove('bg-teal-50/40');
                        return Number(el.getAttribute('data-notification-id'));
                    });
                    markNotificationsAsRead(ids);
                    updateNotificationBadge();
                }
            }
        };

        notificationToggle.addEventListener('click', (event) => {
            event.stopPropagation();
            toggleNotifications();
        });

        document.addEventListener('click', (event) => {
            if (!notificationMenu.contains(event.target) && !notificationToggle.contains(event.target)) {
                notificationMenu.classList.add('invisible', 'scale-95', 'opacity-0');
                notificationMenu.classList.remove('opacity-100', 'scale-100');
            }
        });
    }

    notificationList?.addEventListener('click', (event) => {
        const deleteBtn = event.target.closest('[data-notification-delete]');
        if (!deleteBtn) return;
        event.preventDefault();
        event.stopPropagation();
        const notificationId = Number(deleteBtn.getAttribute('data-notification-delete'));
        const wrapper = deleteBtn.closest('[data-notification-id]');
        if (!wrapper || Number.isNaN(notificationId)) return;

        wrapper.remove();
        updateNotificationBadge();

        fetch(window.APP_URLS.notifications_clear || '/notifications/clear', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': window.CSRF_TOKEN,
            },
            body: JSON.stringify({ ids: [notificationId] }),
        }).catch(() => {
            console.warn('Impossible de supprimer la notification.');
        });

        if (!notificationList.querySelector('[data-notification-id]') && notificationEmptyTemplate) {
            const clone = notificationEmptyTemplate.content.cloneNode(true);
            notificationList.appendChild(clone);
        }
    });

    notificationMarkAllBtn?.addEventListener('click', (event) => {
        event.preventDefault();
        if (!notificationMenu) return;
        const items = notificationMenu.querySelectorAll('[data-notification-id]');
        if (!items.length) return;
        const ids = [];
        items.forEach((item) => {
            const id = Number(item.getAttribute('data-notification-id'));
            if (!Number.isNaN(id)) {
                ids.push(id);
            }
            if (item.getAttribute('data-unread') === 'true') {
                item.setAttribute('data-unread', 'false');
                item.classList.remove('bg-teal-50/40');
            }
        });
        if (ids.length) {
            markNotificationsAsRead(ids);
        } else {
            markNotificationsAsRead();
        }
        updateNotificationBadge();
    });

    updateNotificationBadge();

    function openConfirmModal(form, message) {
        if (!confirmModal || !confirmMessageEl) {
            form.submit();
            return;
        }
        pendingConfirmForm = form;
        const text = (message || 'Confirmer cette action ?').replace(/\\n/g, '\n');
        confirmMessageEl.innerHTML = '';
        const lines = String(text).split('\n');
        lines.forEach((line, index) => {
            const span = document.createElement('span');
            span.textContent = line;
            confirmMessageEl.appendChild(span);
            if (index < lines.length - 1) {
                confirmMessageEl.appendChild(document.createElement('br'));
            }
        });
        confirmModal.classList.remove('hidden');
    }

    function closeConfirmModal() {
        confirmModal?.classList.add('hidden');
        pendingConfirmForm = null;
    }

    confirmApproveBtn?.addEventListener('click', () => {
        if (pendingConfirmForm) {
            const form = pendingConfirmForm;
            closeConfirmModal();
            // Afficher le spinner maintenant que la confirmation est validée
            showLoadingOverlay();
            form.submit();
        }
    });

    confirmCancelBtn?.forEach((btn) => {
        btn.addEventListener('click', () => closeConfirmModal());
    });

    confirmModal?.addEventListener('click', (event) => {
        if (event.target instanceof Element && event.target.hasAttribute('data-confirm-cancel')) {
            closeConfirmModal();
        }
    });

    document.addEventListener('keydown', (event) => {
        if (event.key === 'Escape' && !confirmModal?.classList.contains('hidden')) {
            closeConfirmModal();
        }
    });

    document.querySelectorAll('form[data-confirm]').forEach((form) => {
        form.addEventListener('submit', (event) => {
            if (confirmModal?.classList.contains('hidden')) {
                event.preventDefault();
                openConfirmModal(form, form.getAttribute('data-confirm') || undefined);
            }
        });
    });

    if (profileToggle && profileMenu) {
        const toggleMenu = () => {
            const isOpen = profileMenu.classList.contains('opacity-100');
            profileMenu.classList.toggle('opacity-100', !isOpen);
            profileMenu.classList.toggle('opacity-0', isOpen ? true : false);
            profileMenu.classList.toggle('invisible', isOpen);
            profileMenu.classList.toggle('scale-100', !isOpen);
            profileMenu.classList.toggle('scale-95', isOpen);
        };

        profileToggle.addEventListener('click', (event) => {
            event.stopPropagation();
            toggleMenu();
        });

        document.addEventListener('click', (event) => {
            if (!profileMenu.contains(event.target) && !profileToggle.contains(event.target)) {
                profileMenu.classList.add('invisible', 'scale-95', 'opacity-0');
                profileMenu.classList.remove('opacity-100', 'scale-100');
            }
        });
    }

    function openMobileNav(show) {
        if (!mobileNav || !mobileBackdrop) return;
        mobileNav.classList.toggle('-translate-x-full', !show);
        mobileBackdrop.classList.toggle('hidden', !show);
    }

    mobileToggle && mobileToggle.addEventListener('click', () => {
        const isOpen = !mobileNav?.classList.contains('-translate-x-full');
        openMobileNav(!isOpen);
    });
    mobileClose && mobileClose.addEventListener('click', () => openMobileNav(false));
    mobileBackdrop && mobileBackdrop.addEventListener('click', () => openMobileNav(false));
    
    // Fermer le menu mobile quand on clique sur un lien
    if (mobileNav) {
        mobileNav.querySelectorAll('a.nav-link-mobile').forEach((link) => {
            link.addEventListener('click', () => {
                openMobileNav(false);
            });
        });
    }

    // Gestion du modal d'information sur la page
    const pageInfoToggle = document.querySelector('[data-page-info-toggle]');
    const pageInfoModal = document.getElementById('page-info-modal');
    const pageInfoText = pageInfoModal?.querySelector('[data-page-info-text]');
    const pageInfoContent = document.getElementById('page-info-content');
    const pageInfoCloseBtns = pageInfoModal?.querySelectorAll('[data-page-info-close]');

    function openPageInfoModal() {
        if (!pageInfoModal || !pageInfoText || !pageInfoContent) return;
        const content = pageInfoContent.textContent.trim();
        if (!content) return;
        pageInfoText.textContent = content;
        pageInfoModal.classList.remove('hidden');
        // Animation d'ouverture
        requestAnimationFrame(() => {
            const modalContent = pageInfoModal.querySelector('[data-page-info-content]');
            if (modalContent) {
                modalContent.classList.remove('scale-95', 'opacity-0');
                modalContent.classList.add('scale-100', 'opacity-100');
            }
        });
    }

    function closePageInfoModal() {
        const modalContent = pageInfoModal?.querySelector('[data-page-info-content]');
        if (modalContent) {
            modalContent.classList.remove('scale-100', 'opacity-100');
            modalContent.classList.add('scale-95', 'opacity-0');
        }
        setTimeout(() => {
            pageInfoModal?.classList.add('hidden');
        }, 200);
    }

    pageInfoToggle?.addEventListener('click', (event) => {
        event.stopPropagation();
        openPageInfoModal();
    });

    pageInfoCloseBtns?.forEach((btn) => {
        btn.addEventListener('click', () => closePageInfoModal());
    });

    pageInfoModal?.addEventListener('click', (event) => {
        if (event.target instanceof Element && event.target.hasAttribute('data-page-info-close')) {
            closePageInfoModal();
        }
    });

    document.addEventListener('keydown', (event) => {
        if (event.key === 'Escape' && pageInfoModal && !pageInfoModal.classList.contains('hidden')) {
            closePageInfoModal();
        }
    });
});
