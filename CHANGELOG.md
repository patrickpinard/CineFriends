# Changelog

Tous les changements notables de ce projet sont documentés dans ce fichier.
Format basé sur [Keep a Changelog](https://keepachangelog.com/fr/1.0.0/) — versionnage [Semantic Versioning](https://semver.org/lang/fr/).

---

## [1.2.0] - 2026-03-29

### Ajouté

- **Module Médiathèque** (`app/movies.py`, blueprint `movies_bp`, préfixe `/films`) — partage de films en réseau privé
  - Liste des films avec filtres genre / année / recherche textuelle
  - Fiche détaillée avec affiche TMDB, synopsis, note, genres, réalisateur
  - **Streaming intégré** : remux FFmpeg à la volée (MKV → MP4) pour la compatibilité navigateur ; pool de 2 workers ; requêtes HTTP range supportées ; suivi d'avancement via `/films/<id>/stream-status`
  - **Lecteur vidéo** (`/films/<id>/player`) intégré dans la page
  - **Téléchargement** : fichier unique, épisode individuel ou archive ZIP de tous les épisodes d'une série
  - **Enrichissement TMDB** automatique lors de l'ajout (films et séries) ; rafraîchissement individuel ou en masse (admin)
  - **Favoris** : toggle par utilisateur, page dédiée `/favoris`
  - **Notes** : 1–5 étoiles par utilisateur par film (`UserRating`)
  - **Recommandations** : suggestion de films non vus, avec possibilité de masquage individuel (`HiddenRecommendation`)
  - **Upload** (`/films/ajouter`) : formulaire avec auto-complétion TMDB (films et séries), sélection de fichier depuis le dossier NAS ou upload direct
  - **Scan NAS** : API de détection des fichiers/dossiers non enregistrés (`/films/api/scan-folder`, `/films/api/unregistered-folders`, `/films/api/unregistered-count`)
  - **Diagnostic admin** (`/films/admin/diagnostic`) : vérification de compatibilité des fichiers, test de streaming
  - **Sync TMDB en masse** (`/films/admin/sync-tmdb-bulk`) pour enrichir tous les films non encore liés à TMDB

- **Nouveaux modèles** : `Movie`, `Favorite`, `UserRating`, `HiddenRecommendation`
- **Compteurs utilisateur** : `download_count`, `stream_count`, `login_count` sur le modèle `User`
- **Nouvelles variables de configuration** : `MOVIES_FOLDER`, `TMDB_API_KEY`, `TMDB_LANGUAGE`, `CACHE_TYPE`, `CACHE_REDIS_URL`
- **Nouveaux templates** : `movies/index.html`, `movies/detail.html`, `movies/upload.html`, `movies/player.html`, `movies/diagnostic.html`, `dashboard/favorites.html`
- **`filters.js`** : gestion des filtres dynamiques de la médiathèque côté client

### Modifié

- **README** : entièrement réécrit pour refléter CineFriends (plus TemplateApp) avec documentation de la médiathèque, du streaming, des nouvelles routes et modèles
- **Sidebar** : ajout de l'entrée Médiathèque (`/films/`)
- **Nom du projet** : renommé Dashboard → CineFriends ; remote GitHub mis à jour vers `patrickpinard/CineFriends`

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
