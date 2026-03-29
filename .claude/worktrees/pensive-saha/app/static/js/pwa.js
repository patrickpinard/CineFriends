(function () {
  const showToast = (message, category = 'info') => {
    window.dispatchEvent(
      new CustomEvent('app:toast', {
        detail: { category, message },
      }),
    );
  };

  if ('serviceWorker' in navigator) {
    // Enregistrer immédiatement et aussi au chargement pour iOS
    function registerServiceWorker() {
      navigator.serviceWorker
        .register('/service-worker.js', { scope: '/' })
        .then((registration) => {
          console.log('Service Worker enregistré avec succès:', registration.scope);
          
          // Attendre que le service worker soit activé et contrôle la page
          if (registration.installing) {
            registration.installing.addEventListener('statechange', function() {
              if (this.state === 'activated') {
                console.log('Service Worker activé et contrôle la page');
                // Forcer le contrôle de la page pour iOS
                window.location.reload();
              }
            });
          } else if (registration.waiting) {
            registration.waiting.addEventListener('statechange', function() {
              if (this.state === 'activated') {
                console.log('Service Worker activé');
                window.location.reload();
              }
            });
          } else if (registration.active) {
            console.log('Service Worker déjà actif');
          }
          
          // Vérifier si une mise à jour est disponible
          registration.addEventListener('updatefound', () => {
            const newWorker = registration.installing;
            if (!newWorker) return;
            newWorker.addEventListener('statechange', () => {
              if (newWorker.state === 'installed' && navigator.serviceWorker.controller) {
                showToast('Une nouvelle version est disponible. Rechargez pour l\'appliquer.');
              }
            });
          });
          
          // Vérifier les mises à jour périodiquement (toutes les heures)
          setInterval(() => {
            if (navigator.onLine) {
              registration.update();
            }
          }, 3600000);
        })
        .catch(function (error) {
          console.error('Service worker registration failed:', error);
        });
    }
    
    // Enregistrer immédiatement
    registerServiceWorker();
    
    // Enregistrer aussi au chargement pour iOS Safari
    window.addEventListener('load', registerServiceWorker);

    navigator.serviceWorker.addEventListener('controllerchange', () => {
      showToast('Application mise à jour. Rafraîchissez si nécessaire.', 'success');
    });
    
    // Vérifier que le service worker contrôle la page
    if (navigator.serviceWorker.controller) {
      console.log('Service Worker contrôle la page');
    } else {
      console.log('Service Worker ne contrôle pas encore la page - rechargement nécessaire');
    }
  }

  const isiOS = /iphone|ipad|ipod/i.test(window.navigator.userAgent);
  const isInStandalone = window.matchMedia('(display-mode: standalone)').matches || window.navigator.standalone;

  if (isInStandalone) {
    document.documentElement.classList.add('pwa-standalone');
  }

  const installButton = document.querySelector('[data-pwa-install-trigger]');
  const installModal = document.getElementById('install-modal');
  const installDescription = installModal?.querySelector('[data-install-description]');
  const installStepsDefault = installModal?.querySelector('[data-install-steps="default"]');
  const installStepsIos = installModal?.querySelector('[data-install-steps="ios"]');
  const installActionBtn = installModal?.querySelector('[data-install-action]');
  const installCloseEls = installModal?.querySelectorAll('[data-install-close]');

  let deferredPrompt = null;
  let installMode = 'prompt';

  function showInstallButton() {
    if (!installButton) return;
    installButton.classList.remove('hidden');
  }

  function openInstallModal(mode) {
    if (!installModal || !installDescription || !installStepsDefault || !installStepsIos || !installActionBtn) {
      return;
    }
    installMode = mode;
    if (mode === 'ios') {
      installDescription.textContent = "Ajoutez l’application à votre écran d’accueil pour une expérience plein écran.";
      installStepsIos.classList.remove('hidden');
      installStepsDefault.classList.add('hidden');
      installActionBtn.textContent = 'Compris';
    } else {
      installDescription.textContent = "Installez le Dashboard pour un accès rapide sans navigateur.";
      installStepsIos.classList.add('hidden');
      installStepsDefault.classList.remove('hidden');
      installActionBtn.textContent = 'Installer';
    }
    installModal.classList.remove('hidden');
  }

  function closeInstallModal() {
    installModal?.classList.add('hidden');
  }

  if (isiOS && !isInStandalone) {
    showInstallButton();

    // Banner rapide pour guider l’utilisateur iOS
    const banner = document.createElement('div');
    banner.className = 'fixed inset-x-4 bottom-4 z-50 rounded-2xl border border-white/10 bg-slate-900/90 p-4 text-sm text-slate-100 shadow-lg backdrop-blur';
    banner.innerHTML = "Ajoutez ce dashboard à l'écran d'accueil : <span class='font-semibold text-teal-300'>Partage → Ajouter à l’écran d’accueil</span>.";

    const closeButton = document.createElement('button');
    closeButton.className = 'absolute right-3 top-3 text-xs text-slate-400 hover:text-slate-200';
    closeButton.textContent = 'Fermer';
    closeButton.addEventListener('click', function () {
      banner.remove();
    });

    banner.appendChild(closeButton);
    document.body.appendChild(banner);
  }

  window.addEventListener('beforeinstallprompt', (event) => {
    event.preventDefault();
    deferredPrompt = event;
    showInstallButton();
  });

  window.addEventListener('appinstalled', () => {
    deferredPrompt = null;
    closeInstallModal();
    installButton?.classList.add('hidden');
    document.documentElement.classList.add('pwa-standalone');
  });

  installButton?.addEventListener('click', () => {
    if (deferredPrompt) {
      openInstallModal('prompt');
    } else if (isiOS && !isInStandalone) {
      openInstallModal('ios');
    }
  });

  installActionBtn?.addEventListener('click', async () => {
    if (installMode === 'ios') {
      closeInstallModal();
      return;
    }

    if (!deferredPrompt) {
      closeInstallModal();
      return;
    }

    installActionBtn.disabled = true;
    deferredPrompt.prompt();
    try {
      await deferredPrompt.userChoice;
    } catch (error) {
      console.warn('Installation prompt dismissed', error);
    }
    deferredPrompt = null;
    installActionBtn.disabled = false;
    closeInstallModal();
  });

  installCloseEls?.forEach((el) => {
    el.addEventListener('click', () => closeInstallModal());
  });

  installModal?.addEventListener('click', (event) => {
    if (event.target instanceof Element && event.target.hasAttribute('data-install-close')) {
      closeInstallModal();
    }
  });
})();
