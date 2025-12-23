document.addEventListener('DOMContentLoaded', function () {
    'use strict';
    
    
    // Mettre en cache la page actuelle pour le mode offline
    if ('serviceWorker' in navigator && navigator.serviceWorker.controller) {
        const currentUrl = window.location.href;
        navigator.serviceWorker.controller.postMessage({
            type: 'CACHE_PAGE',
            url: currentUrl
        });
    }

    // --- Journal Accordéon (Ouvrir/Fermer par jour) ---
    const dayToggles = document.querySelectorAll('[data-day-toggle]');
    dayToggles.forEach(toggle => {
        // Initialiser l'état : tous les jours sont fermés par défaut
        const contentId = toggle.getAttribute('aria-controls');
        const content = document.getElementById(contentId);
        if (content && toggle.getAttribute('aria-expanded') === 'false') {
            content.style.maxHeight = '0';
            toggle.classList.add('rounded-xl');
        }
        
        toggle.addEventListener('click', function() {
            const isExpanded = this.getAttribute('aria-expanded') === 'true';
            const contentId = this.getAttribute('aria-controls');
            const content = document.getElementById(contentId);
            const chevron = this.querySelector('[data-day-chevron]');
            
            if (isExpanded) {
                // Fermer
                this.setAttribute('aria-expanded', 'false');
                // Utiliser la hauteur actuelle pour l'animation
                const currentHeight = content.scrollHeight;
                content.style.maxHeight = currentHeight + 'px';
                // Forcer le reflow
                void content.offsetHeight;
                // Puis réduire à 0
                requestAnimationFrame(() => {
                    content.style.maxHeight = '0';
                });
                if (chevron) {
                    chevron.classList.remove('rotate-180');
                }
                this.classList.add('rounded-b-xl');
            } else {
                // Ouvrir
                this.setAttribute('aria-expanded', 'true');
                // Calculer la hauteur réelle du contenu
                content.style.maxHeight = '0';
                const targetHeight = content.scrollHeight;
                // Forcer le reflow
                void content.offsetHeight;
                // Puis animer vers la hauteur cible
                requestAnimationFrame(() => {
                    content.style.maxHeight = targetHeight + 'px';
                });
                // Une fois l'animation terminée, permettre l'expansion automatique
                setTimeout(() => {
                    if (this.getAttribute('aria-expanded') === 'true') {
                        content.style.maxHeight = 'none';
                    }
                }, 300);
                if (chevron) {
                    chevron.classList.add('rotate-180');
                }
                this.classList.remove('rounded-b-xl');
            }
        });
    });

    // --- Journal Accordéon (Ouvrir/Fermer par mois) ---
    const monthToggles = document.querySelectorAll('[data-month-toggle]');
    monthToggles.forEach(toggle => {
        // Initialiser l'état : tous les mois sont fermés par défaut
        const contentId = toggle.getAttribute('aria-controls');
        const content = document.getElementById(contentId);
        if (content && toggle.getAttribute('aria-expanded') === 'false') {
            content.style.maxHeight = '0';
        }
        
        toggle.addEventListener('click', function() {
            const isExpanded = this.getAttribute('aria-expanded') === 'true';
            const contentId = this.getAttribute('aria-controls');
            const content = document.getElementById(contentId);
            const chevron = this.querySelector('[data-month-chevron]');
            
            if (isExpanded) {
                // Fermer
                this.setAttribute('aria-expanded', 'false');
                // Utiliser la hauteur actuelle pour l'animation
                const currentHeight = content.scrollHeight;
                content.style.maxHeight = currentHeight + 'px';
                // Forcer le reflow
                void content.offsetHeight;
                // Puis réduire à 0
                requestAnimationFrame(() => {
                    content.style.maxHeight = '0';
                });
                if (chevron) {
                    chevron.classList.remove('rotate-180');
                }
            } else {
                // Ouvrir
                this.setAttribute('aria-expanded', 'true');
                // Calculer la hauteur réelle du contenu
                content.style.maxHeight = '0';
                const targetHeight = content.scrollHeight;
                // Forcer le reflow
                void content.offsetHeight;
                // Puis animer vers la hauteur cible
                requestAnimationFrame(() => {
                    content.style.maxHeight = targetHeight + 'px';
                });
                // Une fois l'animation terminée, permettre l'expansion automatique
                setTimeout(() => {
                    if (this.getAttribute('aria-expanded') === 'true') {
                        content.style.maxHeight = 'none';
                    }
                }, 300);
                if (chevron) {
                    chevron.classList.add('rotate-180');
                }
            }
        });
    });

    // --- UI Logic (Notifications, Sidebar, Modals) ---
    
    const sidebarToggle = document.querySelector('[data-sidebar-toggle]');
    const body = document.body;
    const SIDEBAR_STORAGE_KEY = 'sidebar_collapsed';
    
    
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


    // Flash messages - utiliser la fonction createToast définie dans base.html
    const flashDataEl = document.getElementById('flash-data');
    if (flashDataEl) {
        try {
            const messages = JSON.parse(flashDataEl.textContent);
            messages.forEach(([category, message]) => {
                window.dispatchEvent(
                    new CustomEvent('app:toast', {
                        detail: { category, message },
                    })
                );
            });
        } catch (e) {
            console.warn('Erreur parsing flash messages:', e);
        }
    }

    // Gestion de la sidebar
    if (sidebarToggle) {
        const isCollapsed = localStorage.getItem(SIDEBAR_STORAGE_KEY) === 'true';
        if (isCollapsed) {
            body.classList.add('sidebar-collapsed');
        }

        sidebarToggle.addEventListener('click', () => {
            const isCollapsed = body.classList.toggle('sidebar-collapsed');
            localStorage.setItem(SIDEBAR_STORAGE_KEY, isCollapsed.toString());
        });
    }

    // Gestion du profil
    if (profileToggle && profileMenu) {
        profileToggle.addEventListener('click', (e) => {
            e.stopPropagation();
            const isOpen = profileMenu.classList.contains('invisible') || profileMenu.classList.contains('opacity-0');
            if (isOpen) {
                profileMenu.classList.remove('invisible', 'opacity-0', 'scale-95');
                profileMenu.classList.add('visible', 'opacity-100', 'scale-100');
            } else {
                profileMenu.classList.add('invisible', 'opacity-0', 'scale-95');
                profileMenu.classList.remove('visible', 'opacity-100', 'scale-100');
            }
        });

        document.addEventListener('click', (e) => {
            if (!profileMenu.contains(e.target) && !profileToggle.contains(e.target)) {
                profileMenu.classList.add('invisible', 'opacity-0', 'scale-95');
                profileMenu.classList.remove('visible', 'opacity-100', 'scale-100');
            }
        });
    }

    // Gestion du menu mobile
    function openMobileNav(open) {
        if (open) {
            mobileNav?.classList.remove('-translate-x-full');
            mobileBackdrop?.classList.remove('hidden');
            document.body.style.overflow = 'hidden';
        } else {
            mobileNav?.classList.add('-translate-x-full');
            mobileBackdrop?.classList.add('hidden');
            document.body.style.overflow = '';
        }
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


    // Gestion des modales de confirmation
    function showConfirmModal(message, form) {
        if (!confirmModal || !confirmMessageEl) return;
        confirmMessageEl.textContent = message;
        pendingConfirmForm = form;
        confirmModal.classList.remove('hidden');
    }

    function hideConfirmModal() {
        if (!confirmModal) return;
        confirmModal.classList.add('hidden');
        pendingConfirmForm = null;
    }

    confirmCancelBtn?.forEach((btn) => {
        btn.addEventListener('click', hideConfirmModal);
    });

    confirmApproveBtn?.addEventListener('click', () => {
        if (pendingConfirmForm) {
            pendingConfirmForm.submit();
        }
        hideConfirmModal();
    });

    confirmModal?.addEventListener('click', (e) => {
        if (e.target === confirmModal) {
            hideConfirmModal();
        }
    });

    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && !confirmModal?.classList.contains('hidden')) {
            hideConfirmModal();
        }
    });

    // Intercepter les formulaires avec data-confirm
    document.querySelectorAll('form[data-confirm]').forEach((form) => {
        form.addEventListener('submit', (e) => {
            e.preventDefault();
            const message = form.getAttribute('data-confirm');
            showConfirmModal(message, form);
        });
    });
});
