# TemplateApp

Application web Flask complète, conçue comme socle prêt à l'emploi pour des projets internes ou embarqués (Raspberry Pi, serveur local). Elle combine un tableau de bord d'administration, la gestion d'utilisateurs, l'authentification sécurisée (2FA), un système de notifications broadcast et une architecture PWA.

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
11. [Emails](#emails)

---

## Fonctionnalités

| Catégorie | Détail |
|-----------|--------|
| Authentification | Connexion/déconnexion, inscription avec validation admin, 2FA par e-mail, réinitialisation de mot de passe, appareils de confiance |
| Gestion utilisateurs | CRUD complet (admin), profil personnel + professionnel, avatar avec validation MIME, historique des modifications (audit) |
| Administration | Page unifiée avec 4 onglets : Utilisateurs, Tâches en attente, Journal, Broadcast |
| Broadcast | Envoi de messages globaux à tous les utilisateurs via modal interactif, niveau déduit automatiquement du titre |
| Notifications | Création par code, niveaux info/warning/error, audience user/admin/global, modal broadcast au chargement de page |
| Tâches admin | Validation ou rejet des inscriptions en attente, groupées par date avec accordéon |
| Journal | Journal d'activité avec filtres par type (connexion, profil, admin, broadcast, messages…) |
| PWA | Service Worker, manifest, icônes dynamiques, mise en cache des pages visitées, mode offline |
| Sécurité | HTTPS/HSTS (Talisman), CSP, CORS, CSRF (WTF), rate limiting (Flask-Limiter), headers HTTP renforcés |
| Sensors (optionnel) | Lecture température DS18B20 (1-Wire), bus I2C |

---

## Architecture

```
TemplateApp/
├── run.py                    # Point d'entrée
├── config.py                 # Configuration multi-environnement
├── app/
│   ├── __init__.py           # Factory Flask (create_app) + inject_globals
│   ├── models.py             # ORM : User, Setting, Notification
│   ├── forms.py              # WTForms : Login, Register, Profile, Reset, 2FA, Broadcast
│   ├── auth.py               # Blueprint auth : login, register, 2FA, reset
│   ├── admin.py              # Blueprint admin : users CRUD, tâches, broadcast
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
│   │       └── page-cache.js # Cache SW des pages visitées
│   └── templates/
│       ├── base.html         # Layout principal (sidebar, header, modal broadcast)
│       ├── auth/             # login, register, twofa, reset
│       └── dashboard/
│           ├── index.html    # Accueil
│           ├── journal.html  # Journal d'activité (admin)
│           ├── profile.html  # Profil utilisateur (onglets pill)
│           ├── users.html    # Administration — Utilisateurs & Tâches
│           ├── broadcast.html # Administration — Broadcast
│           └── tasks.html    # (legacy)
├── migrations/               # Alembic (Flask-Migrate)
└── logs/app.log              # Journal d'activité applicatif
```

**Blueprints :**
- `auth_bp` — préfixe `/auth` — routes publiques d'authentification
- `admin_bp` — préfixe `/admin` — accès réservé aux administrateurs
- `main_bp` — sans préfixe — tableau de bord et fonctionnalités utilisateur

---

## Installation

### Prérequis

- Python 3.10+
- pip
- (optionnel) Node.js pour recompiler Tailwind CSS

### Étapes

```bash
# Cloner le dépôt
git clone https://github.com/patrickpinard/Dashboard.git
cd Dashboard

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

| Variable | Description | Défaut |
|----------|-------------|--------|
| `FLASK_ENV` | `development`, `testing` ou `production` | `development` |
| `FLASK_SECRET_KEY` | Clé secrète (session, CSRF) — **changer en prod** | — |
| `DATABASE_URL` | URI SQLAlchemy (requis en production) | SQLite local |
| `MAIL_SERVER` | Serveur SMTP | — |
| `MAIL_PORT` | Port SMTP | `587` |
| `MAIL_USE_TLS` | Activer TLS | `True` |
| `MAIL_USERNAME` | Identifiant SMTP | — |
| `MAIL_PASSWORD` | Mot de passe SMTP | — |
| `MAIL_DEFAULT_SENDER` | Adresse expéditeur | — |
| `ADMIN_NOTIFICATION_EMAIL` | Email pour alertes admin | — |
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
| `admin` | Tableau de bord complet, gestion utilisateurs, tâches de validation, journal, broadcast |
| `user` | Tableau de bord, profil personnel, notifications |

Le compte administrateur par défaut est créé par `flask seed`. Les nouveaux inscrits via `/auth/register` sont **inactifs** jusqu'à validation manuelle par un admin (onglet Tâches de la page Administration).

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
| `GET /camera` | Page caméra |
| `GET /parametres` | Paramètres |
| `GET /journal` | Journal d'activité (admin) — filtres + accordéon par mois/jour |
| `GET/POST /profil` | Profil utilisateur avec onglets (Identité, Pro, Sécurité, Notifications) |

### Administration (`/admin/`)

| Route | Description |
|-------|-------------|
| `GET /admin/utilisateurs` | Page Administration — onglet Utilisateurs (filtres, tri, pagination) |
| `GET /admin/utilisateurs?tab=pending` | Page Administration — onglet Tâches (inscriptions en attente) |
| `GET/POST /admin/utilisateurs/nouveau` | Créer un utilisateur |
| `GET/POST /admin/utilisateurs/<id>/modifier` | Modifier un utilisateur |
| `POST /admin/utilisateurs/<id>/supprimer` | Supprimer un utilisateur |
| `POST /admin/utilisateurs/<id>/reinitialiser-mot-de-passe` | Envoyer un lien de réinitialisation |
| `POST /admin/utilisateurs/<id>/approuver` | Approuver une inscription en attente |
| `POST /admin/utilisateurs/<id>/rejeter` | Rejeter et supprimer une inscription |
| `GET/POST /admin/notifications/broadcast` | Envoyer une notification globale (Broadcast) |

### API & PWA

| Route | Description |
|-------|-------------|
| `GET /health` | Vérification état app + BDD (JSON) |
| `GET /api/server-time` | Heure serveur locale + UTC (JSON) |
| `GET /api/notifications/broadcasts` | Liste des broadcasts récents (30 j) pour le modal (JSON) |
| `GET /manifest.json` | Manifest PWA |
| `GET /service-worker.js` | Service Worker |
| `GET /icon/<size>.png` | Icône dynamique (180, 192, 256, 512 px) |
| `POST /notifications/read` | Marquer notification(s) comme lues |
| `POST /notifications/clear` | Supprimer / effacer notifications |

---

## Modèles de données

### User

Champs principaux : `id`, `username`, `password_hash`, `email`, `active`, `role`, `last_login`, `created_at`

Informations personnelles : `title`, `first_name`, `last_name`, `date_of_birth`, `bio`, `avatar_filename`, `phone`, `phone_mobile`, `street`, `postal_code`, `city`, `country`

Informations professionnelles : `company`, `job_title`, `email_professional`, `website`, `linkedin`, et adresse professionnelle complète

Authentification 2FA : `twofa_enabled`, `twofa_code_hash`, `twofa_code_sent_at`, `twofa_trusted_token_hash`, `twofa_trusted_created_at`

### Notification

Champs : `id`, `user_id` (nullable pour les globales), `audience` (`user`/`admin`/`global`), `level` (`info`/`warning`/`error`), `title`, `message`, `action_url`, `created_at`, `read`, `persistent`

Les notifications `audience=global` sont affichées comme **modal broadcast** à tous les utilisateurs connectés. Le suivi "déjà vu" est géré par `localStorage` côté client (clé `seen_broadcasts`) pour éviter les problèmes de lecture partagée sur le flag `read`.

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

---

## PWA & Offline

L'application est installable comme Progressive Web App :
- Manifest JSON dynamique avec icônes générées à la volée
- Service Worker avec cache des ressources statiques et de la dernière page visitée
- `base-init.js` enregistre le SW immédiatement (compatible iOS Safari)
- `page-cache.js` envoie un message `CACHE_PAGE` au SW à chaque navigation
- Page `/offline.html` servie quand la connexion est indisponible

---

## Emails

Les emails sont envoyés via SMTP avec `threading.Thread` (non-bloquant).

Emails déclenchés :
- Bienvenue après approbation d'un compte
- Code 2FA lors de la connexion
- Lien de réinitialisation de mot de passe
- Notification aux admins lors d'une nouvelle inscription

Configuration dans `.env` : `MAIL_SERVER`, `MAIL_PORT`, `MAIL_USE_TLS`, `MAIL_USERNAME`, `MAIL_PASSWORD`, `MAIL_DEFAULT_SENDER`
