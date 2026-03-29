/**
 * Applique dynamiquement les styles d'avatar basés sur les attributs data-*
 * pour éviter les styles inline bloqués par la CSP.
 */
(function() {
    'use strict';
    
    function applyAvatarStyles() {
        // Appliquer les styles pour les avatars avec gradient
        const avatarGradients = document.querySelectorAll('[data-avatar-gradient]');
        avatarGradients.forEach(function(avatar) {
            const gradient = avatar.getAttribute('data-avatar-gradient');
            const shadow = avatar.getAttribute('data-avatar-shadow');
            if (gradient) {
                avatar.style.background = gradient;
            }
            if (shadow) {
                avatar.style.boxShadow = shadow;
            }
        });
        
        // Appliquer les styles pour les avatars avec photo (seulement shadow)
        const avatarShadows = document.querySelectorAll('[data-avatar-shadow-only]');
        avatarShadows.forEach(function(avatar) {
            const shadow = avatar.getAttribute('data-avatar-shadow-only');
            if (shadow) {
                avatar.style.boxShadow = shadow;
            }
        });
    }
    
    // Appliquer les styles lorsque le DOM est prêt
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', applyAvatarStyles);
    } else {
        applyAvatarStyles();
    }
})();

