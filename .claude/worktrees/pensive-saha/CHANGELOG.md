# Changelog

Tous les changements notables de ce projet sont documentés dans ce fichier.
Format basé sur [Keep a Changelog](https://keepachangelog.com/fr/1.0.0/) — versionnage [Semantic Versioning](https://semver.org/lang/fr/).

---

## [1.1.0] - 2026-03-26

### Ajouté

- **Page Administration unifiée** : 4 onglets dans une seule vue (Utilisateurs, Tâches, Journal, Broadcast)
- **Broadcast** : formulaire d'envoi de notifications globales avec liste de titres prédéfinis (`<datalist>`) et détection automatique du niveau (info/warning/error) côté serveur selon le titre
- **Modal broadcast global** : les notifications `audience=global` s'affichent en modal centré à tous les utilisateurs connectés ; suivi "déjà vu" par `localStorage` (clé `seen_broadcasts`) pour éviter les problèmes de flag `read` partagé
- **Flou du header** lors de l'ouverture du modal broadcast (inline style JS, compatible CSS compilé statique)
- **API `/api/notifications/broadcasts`** : endpoint `GET` renvoyant les broadcasts des 30 derniers jours, contourné avec `cache: 'no-store'` pour bypasser le Service Worker
- **Journal — filtre Broadcast** : nouveau type `broadcast` dans les filtres et dans les patterns de classification des entrées de journal
- **Attribut `data-app-header`** sur l'élément `<header>` pour le ciblage JS du flou

### Modifié

- **Boutons d'action utilisateurs** : passage de cercles icône seule (`h-8 w-8`) à des pills icône + texte (Modifier, Mot de passe, Supprimer) — desktop et mobile
- **Bouton "Mot de passe"** ajouté dans les cartes mobiles (manquait par rapport au desktop)
- **Onglet Profil** : tabs refaits avec le style pill/nav (`rounded-2xl border bg-slate-50 p-1`) cohérent avec la page Administration
- **Séparateur visuel** entre la barre de recherche et la liste des tâches dans l'onglet Tâches
- **Journal** : renommage du type `AUTRE` → `MESSAGES` dans les labels, filtres et couleurs
- **Modal de confirmation** : bouton adaptatif selon `data-confirm-variant` — vert "Confirmer" pour les resets de mot de passe, rouge "Supprimer" pour les suppressions
- **Broadcast** : champ `persistent` supprimé du formulaire (fixé à `False` côté serveur) ; champ `level` supprimé du formulaire (détection automatique via `_detect_broadcast_level()`)
- **Navigation mobile** : 4 entrées admin séparées fusionnées en une seule entrée "Administration" avec badge de tâches en attente

### Corrigé

- **TypeError offset-naive/aware** dans `auth.py` : `u.reset_token_expires > utcnow()` corrigé avec `to_utc_aware(u.reset_token_expires) > utcnow()` (SQLite stocke les datetimes sans timezone)
- **Modal broadcast invisible** : plusieurs causes résolues — classes Tailwind arbitraires (`z-[60]`, `bg-slate-900/60`) non présentes dans le CSS compilé statique remplacées par des valeurs compilées ou des inline styles ; styles de couleur du bouton Accepter et de l'icône injectés en JS inline
- **Centrage vertical du modal** : `flex min-h-full items-center` remplacé par `absolute inset-0 flex items-center justify-center`
- **Notifications broadcast** : suppression du filtre `read=False` (flag global cassé dès qu'un utilisateur lisait la notif) ; remplacement par une fenêtre glissante de 30 jours

### Supprimé

- Système de **toasts** (fichier `toast.js` conservé mais vidé, `#toast-container` retiré de `base.html`)
- Fichiers Docker (`Dockerfile`, `docker-compose.yml`, `.dockerignore`) — hors scope du projet
- Fichiers de documentation anciens (`ANALYSE_ET_AMELIORATIONS.md`, `DOCUMENTATION.md`, `MIGRATION_GUIDE.md`, `README_AMELIORATIONS.md`)

---

## [1.0.0] - 2025-01-XX

### Fonctionnalités initiales

- Authentification complète (login, register, 2FA par e-mail, reset password, appareils de confiance)
- Gestion des utilisateurs : CRUD admin, profil personnel + professionnel, avatar (validation MIME)
- Système de notifications (user / admin / global, niveaux info/warning/error)
- Progressive Web App : Service Worker, manifest, icônes dynamiques, mode offline
- Journal d'activité avec accordéon par mois/jour
- Logging structuré dans `logs/app.log`
- Sécurité : Flask-Talisman, Flask-Limiter, Flask-WTF CSRF, CORS
- Templates Tailwind CSS compilés (CSS statique, pas de JIT)
- Refactoring routes en package `app/routes/` (dashboard, profile, notifications, pwa)
