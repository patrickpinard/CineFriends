// Gestion des onglets pour la page de profil
(function() {
    'use strict';
    
    function initProfileTabs() {
        var tabButtons = document.querySelectorAll('.tab-button[data-tab]');
        var tabContents = document.querySelectorAll('.tab-content[id^="tab-"]');

        if (!tabButtons || tabButtons.length === 0 || !tabContents || tabContents.length === 0) {
            return;
        }

        function showTab(tabName) {
            // Masquer tous les contenus
            for (var i = 0; i < tabContents.length; i++) {
                tabContents[i].classList.add('hidden');
            }

            // Réinitialiser tous les boutons
            for (var i = 0; i < tabButtons.length; i++) {
                var btn = tabButtons[i];
                btn.classList.remove('active-tab', 'bg-white', 'text-slate-900', 'shadow-sm');
                btn.classList.add('text-slate-500');
            }

            // Afficher le contenu ciblé
            var targetContent = document.getElementById('tab-' + tabName);
            if (targetContent) {
                targetContent.classList.remove('hidden');
            }

            // Activer le bouton correspondant
            for (var i = 0; i < tabButtons.length; i++) {
                var btn = tabButtons[i];
                if (btn.getAttribute('data-tab') === tabName) {
                    btn.classList.remove('text-slate-500');
                    btn.classList.add('active-tab', 'bg-white', 'text-slate-900', 'shadow-sm');
                    break;
                }
            }
        }

        // Attacher les événements de clic
        for (var i = 0; i < tabButtons.length; i++) {
            tabButtons[i].addEventListener('click', function(e) {
                e.preventDefault();
                var tabName = this.getAttribute('data-tab');
                if (tabName) {
                    showTab(tabName);
                }
            });
        }

        // Afficher le premier onglet par défaut (photo)
        if (tabButtons.length > 0) {
            var firstTabName = tabButtons[0].getAttribute('data-tab');
            if (firstTabName) {
                showTab(firstTabName);
            }
        }
    }

    // Initialiser quand le DOM est prêt
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initProfileTabs);
    } else {
        initProfileTabs();
    }
})();

