# CineFriends

Application web Flask de partage de films en réseau privé. Les membres consultent, streament et téléchargent des films stockés sur un serveur local ou NAS, avec enrichissement automatique des métadonnées via l'API TMDB.

---

## Sommaire

1. [Fonctionnalités](#fonctionnalités)
2. [Architecture](#architecture)
3. [Installation](#installation)
4. [Configuration](#configuration)
5. [Lancer l'application](#lancer-lapplication)
6. [Comptes et rôles](#comptes-et-rôles)
7. [Pages et routes](#pages-et-routes)
8. [Modèles de données](#modèles-de-données)
9. [Sécurité](#sécurité)
10. [PWA & Offline](#pwa--offline)
11. [Streaming & FFmpeg](#streaming--ffmpeg)
12. [Emails](#emails)

---

## Fonctionnalités

| Catégorie | Détail |
|-----------|--------|
| Médiathèque | Liste des films avec filtres genre/année/recherche, fiches détaillées, affiches TMDB |
| Streaming | Lecture en ligne avec remux FFmpeg à la volée (MKV → MP4 compatible navigateur) |
| Téléchargement | Téléchargement direct ou par épisode, archive ZIP pour les séries |
| TMDB | Enrichissement automatique des métadonnées (titre, synopsis, affiche, note, genres, réalisateur) |
| Favoris | Mise en favori des films par utilisateur |
| Notes | Notation 1–5 étoiles par utilisateur |
| Recommandations | Suggestion de films non vus, masquage individuel possible |
| Upload | Ajout de films avec recherche TMDB assistée (auto-complétion) |
| Scan NAS | Détection des fichiers non enregistrés sur le dossier films |
| Authentification | Connexion/déconnexion, inscription avec validation admin, 2FA par e-mail, réinitialisation de mot de passe, appareils de confiance |
| Gestion utilisateurs | CRUD complet (admin), profil personnel + professionnel, avatar avec validation MIME, historique des modifications (audit) |
| Administration | Page unifiée : Utilisateurs, Tâches en attente, Journal, Broadcast |
| Broadcast | Envoi de messages globaux à tous les utilisateurs via modal interactif |
| Notifications | Niveaux info/warning/error, audience user/admin/global, modal broadcast au chargement de page |
| PWA | Service Worker, manifest, icônes dynamiques, mise en cache, mode offline |
| Sécurité | HTTPS/HSTS (Talisman), CSP, CORS, CSRF (WTF), rate limiting (Flask-Limiter), headers HTTP renforcés |

---

## Architecture

```
CineFriends/
├── run.py                    # Point d'entrée
├── config.py                 # Configuration multi-environnement
├── app/
│   ├── __init__.py           # Factory Flask (create_app) + inject_globals
│   ├── models.py             # ORM : User, Movie, Favorite, UserRating, HiddenRecommendation, Notification, Setting
│   ├── forms.py              # WTForms : Login, Register, Profile, Reset, 2FA, Broadcast
│   ├── auth.py               # Blueprint auth : login, register, 2FA, reset
│   ├── admin.py              # Blueprint admin : users CRUD, tâches, broadcast
│   ├── movies.py             # Blueprint movies : médiathèque, streaming, TMDB
│   ├── services.py           # Services métier : create_notification
│   ├── mailer.py             # Envoi d'emails (SMTP, async threading)
│   ├── utils.py              # Utilitaires : avatar, datetime, populate_form
│   ├── security.py           # Config CORS + Talisman
│   ├── routes/               # Blueprint principal (main_bp)
│   │   ├── dashboard.py      # /, /journal, /graphiques, etc.
│   │   ├── profile.py        # /profil
│   │   ├── notifications.py  # /notifications/read, /clear, /api/broadcasts
│   │   └── pwa.py            # manifest, SW, health, error handlers
│   ├── static/
│   │   ├── css/main.css      # Styles compilés Tailwind (statique)
│   │   └── js/
│   │       ├── main.js       # Sidebar, profil, mobile nav, modales de confirmation
│   │       ├── base-init.js  # Service Worker + notifications broadcast (modal global)
│   │       ├── profile-tabs.js # Logique des onglets du profil
│   │       ├── avatar-styles.js # Gradients et ombres d'avatars
│   │       ├── filters.js    # Filtres dynamiques médiathèque
│   │       └── page-cache.js # Cache SW des pages visitées
│   └── templates/
│       ├── base.html         # Layout principal (sidebar, header, modal broadcast)
│       ├── auth/             # login, register, twofa, reset
│       ├── dashboard/
│       │   ├── index.html    # Accueil
│       │   ├── journal.html  # Journal d'activité (admin)
│       │   ├── profile.html  # Profil utilisateur (onglets pill)
│       │   ├── favorites.html # Favoris de l'utilisateur
│       │   ├── users.html    # Administration — Utilisateurs & Tâches
│       │   └── broadcast.html # Administration — Broadcast
│       └── movies/
│           ├── index.html    # Liste des films (filtres)
│           ├── detail.html   # Fiche film + boutons streaming/téléchargement
│           ├── upload.html   # Formulaire d'ajout avec recherche TMDB
│           ├── player.html   # Lecteur vidéo intégré
│           └── diagnostic.html # Diagnostic admin (compatibilité fichiers)
├── films/                    # Dossier des fichiers vidéo (configurable via MOVIES_FOLDER)
├── migrations/               # Alembic (Flask-Migrate)
└── logs/app.log              # Journal d'activité applicatif
```

**Blueprints :**
- `auth_bp` — préfixe `/auth` — routes publiques d'authentification
- `admin_bp` — préfixe `/admin` — accès réservé aux administrateurs
- `movies_bp` — préfixe `/films` — médiathèque, streaming, TMDB
- `main_bp` — sans préfixe — tableau de bord et fonctionnalités utilisateur

---

## Installation

### Prérequis

- Python 3.10+
- pip
- FFmpeg (pour le streaming/remux)
- (optionnel) Node.js pour recompiler Tailwind CSS

### Étapes

```bash
# Cloner le dépôt
git clone https://github.com/patrickpinard/CineFriends.git
cd CineFriends

# Créer l'environnement virtuel
python3 -m venv .venv
source .venv/bin/activate        # Linux/macOS
# .venv\Scripts\activate         # Windows

# Installer les dépendances Python
pip install -r requirements.txt

# Copier et éditer la configuration
cp .env.example .env             # adapter les valeurs

# Initialiser la base de données
flask db upgrade

# Créer l'administrateur par défaut
flask seed
```

---

## Configuration

Toutes les variables sont chargées depuis un fichier `.env` (ou variables d'environnement système).

### Application

| Variable | Description | Défaut |
|----------|-------------|--------|
| `FLASK_ENV` | `development`, `testing` ou `production` | `development` |
| `FLASK_SECRET_KEY` | Clé secrète (session, CSRF) — **changer en prod** | — |
| `DATABASE_URL` | URI SQLAlchemy (requis en production) | SQLite local |

### Médiathèque

| Variable | Description | Défaut |
|----------|-------------|--------|
| `MOVIES_FOLDER` | Chemin absolu vers le dossier des fichiers vidéo | `./films` |
| `TMDB_API_KEY` | Clé API TMDB pour l'enrichissement des métadonnées | — |
| `TMDB_LANGUAGE` | Langue des métadonnées TMDB | `fr-FR` |
| `CACHE_TYPE` | Type de cache Flask-Caching (`simple`, `redis`) | `simple` |
| `CACHE_REDIS_URL` | URL Redis si `CACHE_TYPE=redis` | — |

### Email

| Variable | Description | Défaut |
|----------|-------------|--------|
| `MAIL_SERVER` | Serveur SMTP | — |
| `MAIL_PORT` | Port SMTP | `587` |
| `MAIL_USE_TLS` | Activer TLS | `True` |
| `MAIL_USERNAME` | Identifiant SMTP | — |
| `MAIL_PASSWORD` | Mot de passe SMTP | — |
| `MAIL_DEFAULT_SENDER` | Adresse expéditeur | — |
| `ADMIN_NOTIFICATION_EMAIL` | Email pour alertes admin | — |

### Sécurité & divers

| Variable | Description | Défaut |
|----------|-------------|--------|
| `CORS_ORIGINS` | Origines CORS autorisées (virgule) | — |
| `LOG_LEVEL` | `INFO` ou `DEBUG` | `INFO` |

---

## Lancer l'application

```bash
# Développement
source .venv/bin/activate
python run.py
# → http://localhost:8080

# Production (exemple Gunicorn)
gunicorn "app:create_app('production')" -w 4 -b 0.0.0.0:8080
```

---

## Comptes et rôles

| Rôle | Accès |
|------|-------|
| `admin` | Tableau de bord complet, gestion utilisateurs, tâches de validation, journal, broadcast, ajout/suppression de films, diagnostic |
| `user` | Médiathèque, streaming, téléchargement, favoris, notes, profil personnel, notifications |

Le compte administrateur par défaut est créé par `flask seed`. Les nouveaux inscrits via `/auth/register` sont **inactifs** jusqu'à validation manuelle par un admin.

---

## Pages et routes

### Authentification (`/auth/`)

| Route | Description |
|-------|-------------|
| `GET/POST /auth/login` | Formulaire de connexion |
| `GET/POST /auth/register` | Inscription (compte inactif en attente) |
| `GET /auth/inscription-en-attente` | Confirmation d'inscription |
| `GET/POST /auth/2fa` | Vérification du code 2FA |
| `GET/POST /auth/reset-password` | Demande de réinitialisation |
| `GET/POST /auth/reset-password/<token>` | Nouveau mot de passe via token |
| `GET /auth/logout` | Déconnexion |

### Tableau de bord (`/`)

| Route | Description |
|-------|-------------|
| `GET /` | Accueil |
| `GET /graphiques` | Page graphiques |
| `GET /automatisation` | Page automatisation |
| `GET /journal` | Journal d'activité (admin) |
| `GET/POST /profil` | Profil utilisateur (onglets Identité, Pro, Sécurité, Notifications) |
| `GET /favoris` | Films favoris de l'utilisateur |

### Médiathèque (`/films/`)

| Route | Description |
|-------|-------------|
| `GET /films/` | Liste des films (filtres genre/année/recherche) |
| `GET /films/<id>` | Fiche détaillée + streaming + téléchargement |
| `GET/POST /films/ajouter` | Formulaire d'ajout avec recherche TMDB |
| `GET /films/<id>/player` | Lecteur vidéo intégré |
| `GET /films/<id>/player/episode` | Lecteur épisode de série |
| `GET /films/<id>/stream` | Flux vidéo (range requests, remux FFmpeg) |
| `GET /films/<id>/stream/episode` | Flux épisode |
| `GET /films/<id>/stream-status` | État du remux en cours (JSON) |
| `GET /films/<id>/telecharger` | Téléchargement du fichier principal |
| `GET /films/<id>/telecharger/episode` | Téléchargement d'un épisode |
| `GET /films/<id>/telecharger/tous` | Téléchargement de tous les épisodes (ZIP) |
| `POST /films/<id>/supprimer` | Suppression (admin) |
| `POST /films/<id>/favori` | Ajouter/retirer des favoris |
| `POST /films/<id>/noter` | Donner une note 1–5 |
| `POST /films/<id>/hide-recommendation` | Masquer des recommandations |
| `POST /films/<id>/refresh-tmdb` | Rafraîchir les métadonnées TMDB |
| `POST /films/admin/sync-tmdb-bulk` | Synchronisation TMDB en masse (admin) |

### API Médiathèque

| Route | Description |
|-------|-------------|
| `GET /films/api/search` | Recherche TMDB films (AJAX JSON) |
| `GET /films/api/search/tv` | Recherche TMDB séries (AJAX JSON) |
| `GET /films/api/details/<tmdb_id>` | Détails TMDB film (AJAX JSON) |
| `GET /films/api/details/tv/<tmdb_id>` | Détails TMDB série (AJAX JSON) |
| `GET /films/api/scan-folder` | Scanner le dossier films (JSON) |
| `GET /films/api/unregistered-folders` | Dossiers non enregistrés (JSON) |
| `GET /films/api/unregistered-count` | Nombre de fichiers non enregistrés (JSON) |
| `GET /films/api/compat-check` | Vérification compatibilité navigateur (JSON) |
| `GET /films/<id>/stream-test` | Test de streaming (JSON) |
| `GET /films/admin/diagnostic` | Page diagnostic admin |

### Administration (`/admin/`)

| Route | Description |
|-------|-------------|
| `GET /admin/utilisateurs` | Page Administration — onglet Utilisateurs |
| `GET /admin/utilisateurs?tab=pending` | Page Administration — onglet Tâches |
| `GET/POST /admin/utilisateurs/nouveau` | Créer un utilisateur |
| `GET/POST /admin/utilisateurs/<id>/modifier` | Modifier un utilisateur |
| `POST /admin/utilisateurs/<id>/supprimer` | Supprimer un utilisateur |
| `POST /admin/utilisateurs/<id>/reinitialiser-mot-de-passe` | Envoyer un lien de réinitialisation |
| `POST /admin/utilisateurs/<id>/approuver` | Approuver une inscription |
| `POST /admin/utilisateurs/<id>/rejeter` | Rejeter et supprimer une inscription |
| `GET/POST /admin/notifications/broadcast` | Envoyer une notification globale |

### API & PWA

| Route | Description |
|-------|-------------|
| `GET /health` | Vérification état app + BDD (JSON) |
| `GET /api/server-time` | Heure serveur locale + UTC (JSON) |
| `GET /api/notifications/broadcasts` | Broadcasts des 30 derniers jours (JSON) |
| `GET /manifest.json` | Manifest PWA |
| `GET /service-worker.js` | Service Worker |
| `GET /icon/<size>.png` | Icône dynamique |
| `POST /notifications/read` | Marquer notification(s) comme lues |
| `POST /notifications/clear` | Supprimer / effacer notifications |

---

## Modèles de données

### User

Champs principaux : `id`, `username`, `password_hash`, `email`, `active`, `role`, `last_login`, `created_at`, `login_count`, `download_count`, `stream_count`

Informations personnelles : `title`, `first_name`, `last_name`, `date_of_birth`, `bio`, `avatar_filename`, `phone`, `phone_mobile`, `street`, `postal_code`, `city`, `country`

Informations professionnelles : `company`, `job_title`, `email_professional`, `website`, `linkedin`, et adresse professionnelle complète

Authentification 2FA : `twofa_enabled`, `twofa_code_hash`, `twofa_code_sent_at`, `twofa_trusted_token_hash`, `twofa_trusted_created_at`

### Movie

Champs : `id`, `title`, `original_title`, `year`, `genres`, `director`, `overview`, `poster_url`, `tmdb_id`, `language`, `rating`, `file_filename`, `file_size`, `uploaded_by_id`, `created_at`, `download_count`

Enrichi automatiquement via TMDB lors de l'ajout ou du rafraîchissement. Les fichiers vidéo sont stockés dans `MOVIES_FOLDER` et référencés par `file_filename`.

### Favorite

Relation many-to-many User ↔ Movie : `id`, `user_id`, `movie_id`

### UserRating

Note 1–5 étoiles par utilisateur par film : `id`, `user_id`, `movie_id`, `rating`

### HiddenRecommendation

Films masqués des recommandations : `id`, `user_id`, `movie_id`

### Notification

Champs : `id`, `user_id` (nullable pour les globales), `audience` (`user`/`admin`/`global`), `level` (`info`/`warning`/`error`), `title`, `message`, `action_url`, `created_at`, `read`, `persistent`

Les notifications `audience=global` s'affichent en **modal broadcast** à tous les utilisateurs. Le suivi "déjà vu" est géré par `localStorage` (clé `seen_broadcasts`) côté client.

### Setting

Stockage clé/valeur pour les paramètres applicatifs : `key`, `value`, `updated_at`

---

## Sécurité

- **Mots de passe** : hachage PBKDF2-SHA256 (Werkzeug)
- **CSRF** : protection sur tous les formulaires (Flask-WTF)
- **Rate limiting** : Flask-Limiter (5/min sur login, 3/h sur register et reset)
- **Headers HTTP** : Flask-Talisman (HSTS, X-Frame-Options, X-Content-Type-Options, Referrer-Policy)
- **CSP** : Content Security Policy configurée dans `security.py`
- **CORS** : origines contrôlées via variable `CORS_ORIGINS`
- **Validation des uploads** : extension + MIME réel via Pillow (`img.verify()`)
- **Cookies** : `HttpOnly`, `SameSite=Lax`, `Secure` en production
- **Streaming** : vérification `login_required` sur toutes les routes de fichiers

---

## PWA & Offline

L'application est installable comme Progressive Web App :
- Manifest JSON dynamique avec icônes générées à la volée
- Service Worker avec cache des ressources statiques et de la dernière page visitée
- `base-init.js` enregistre le SW immédiatement (compatible iOS Safari)
- `page-cache.js` envoie un message `CACHE_PAGE` au SW à chaque navigation
- Page `/offline.html` servie quand la connexion est indisponible

---

## Streaming & FFmpeg

Le streaming s'appuie sur FFmpeg pour assurer la compatibilité navigateur :

- Les fichiers `.mkv` (et autres conteneurs incompatibles) sont **remuxés à la volée** vers MP4 (H.264/AAC) dans un dossier de cache
- Un pool de 2 workers FFmpeg (`ThreadPoolExecutor`) limite la saturation CPU
- Les requêtes HTTP range sont supportées pour la lecture partielle et le seek
- `/films/<id>/stream-status` permet au player de suivre l'avancement du remux
- Les fichiers déjà compatibles (MP4 natif) sont streamés directement sans remux

---

## Emails

Les emails sont envoyés via SMTP avec `threading.Thread` (non-bloquant).

Emails déclenchés :
- Bienvenue après approbation d'un compte
- Code 2FA lors de la connexion
- Lien de réinitialisation de mot de passe
- Notification aux admins lors d'une nouvelle inscription
- Notification de désactivation de compte
