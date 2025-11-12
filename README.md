# Dashboard

Application web complète construite avec Flask pour piloter un tableau de bord d’automatisation. Elle intègre une Progressive Web App optimisée iPhone, une gestion avancée des utilisateurs (rôles, 2FA, avatars, notifications), un module d’automatisation, le streaming caméra, des paramètres centralisés et un journal d’audit détaillé.

## Sommaire

1. [Fonctionnalités principales](#fonctionnalités-principales)
2. [Architecture & technologies](#architecture--technologies)
3. [Prérequis](#prérequis)
4. [Configuration](#configuration)
5. [Installation](#installation)
6. [Lancement de l’application](#lancement-de-lapplication)
7. [Structure du projet](#structure-du-projet)
8. [Gestion des utilisateurs](#gestion-des-utilisateurs)
9. [Sécurité & authentification forte](#sécurité--authentification-forte)
10. [Automatisation](#automatisation)
11. [Journal & notifications](#journal--notifications)
12. [PWA & expérience mobile](#pwa--expérience-mobile)
13. [Envoi d’e-mails](#envoi-demails)
14. [Développement & bonnes pratiques](#développement--bonnes-pratiques)
15. [Capteurs & relais](#capteurs--relais)
16. [Documentation détaillée des fichiers](#documentation-détaillée-des-fichiers)
17. [Dépannage](#dépannage)

## Fonctionnalités principales

- **Dashboard** : vue synthétique des activités récentes avec graphique interactif (ApexCharts), cartes capteurs (valeur courante + min/max 24h) et alertes sécurité.
- **Automatisation** : création de règles, recherche/filtre/sort, confirmation de suppression, affichage structuré déclencheur/actions, responsive complet.
- **Caméra USB** : flux vidéo intégré dans une carte responsive adaptée aux appareils iOS.
- **Paramètres** : formulaire de configuration applicative harmonisé avec le design global.
- **Gestion des utilisateurs** : création, édition, validation des inscriptions, avatars, 2FA, filtres contextuels, vue mobile optimisée.
- **Journal** : audit détaillé (avant/après, auteur, type d’évènement), purge filtrée par date, accès restreint aux administrateurs.
- **Notifications** : toasts centralisés, centre de notifications persistant, alertes administrateur sur évènements critiques.
- **PWA iPhone** : manifest, service worker, installation guidée, détection de mise à jour, bottom bar mobile, safe areas.

## Architecture & technologies

- **Backend** : Flask, Flask-Login, Flask-WTF, SQLAlchemy.
- **Frontend** : Tailwind CSS (via CDN), composants responsive, toasts dynamiques, ApexCharts pour les mesures climatiques.
- **Auth** : sessions sécurisées, rôles, double authentification par e-mail, gestion des appareils de confiance.
- **PWA** : `manifest.json`, `service-worker.js`, prise en charge iOS (icônes `icon-128.png`, `icon-512.png`).
- **Base de données** : SQLite par défaut (`instance/dashboard.db`).
- **Emails** : `smtplib` sécurisé, templates HTML/texte harmonisés.
- **Utilitaires** : avatars dynamiques, stockage uploads, notifications persistantes.

## Prérequis

- Python 3.11+ recommandé (testée sur 3.13).
- Outils de compilation (`build-essential` sur Linux) pour dépendances Python natives.
- Accès SMTP pour l’envoi de mails (TLS).
- macOS : utiliser un environnement virtuel pour éviter le message `externally-managed-environment` (cf. dépannage).

## Configuration

Créer un fichier `.env` à la racine (exemple minimal) :

```
FLASK_ENV=development
SECRET_KEY=change-me
SQLALCHEMY_DATABASE_URI=sqlite:///instance/dashboard.db

MAIL_SERVER=smtp.example.com
MAIL_PORT=587
MAIL_USE_TLS=true
MAIL_USERNAME=bot@example.com
MAIL_PASSWORD=super-secret
MAIL_DEFAULT_SENDER="Dashboard" <bot@example.com>
MAIL_MONITOR_ADDRESS=security@example.com
ADMIN_NOTIFICATION_EMAIL=admin@example.com

TWOFA_CODE_TTL_SECONDS=300
TWOFA_TRUSTED_DEVICE_TTL_DAYS=30

UPLOAD_FOLDER=app/static/uploads
MAX_CONTENT_LENGTH=4 * 1024 * 1024
```

> Les valeurs définies dans `.env` surchargent celles de `config.py`. Le dossier `app/static/uploads` est créé automatiquement.

## Installation

```bash
python3 -m venv .venv
source .venv/bin/activate  # sous Windows : .venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt
```

### Alimentation de la base

```bash
flask --app run.py shell <<'PY'
from app import db
from app.models import User

db.create_all()

admin = User(username="admin", email="admin@example.com")
admin.set_password("admin")
admin.role = "admin"
admin.active = True
db.session.add(admin)
db.session.commit()
PY
```

Cette commande crée la base et un compte administrateur par défaut (`admin/admin`).

## Lancement de l’application

```bash
python run.py
# ou
flask --app run.py run --debug --port 8080
```

L’application écoute par défaut sur `http://127.0.0.1:8080`.

## Structure du projet

```
.
├── app/
│   ├── __init__.py          # création de l’app, extensions, blueprints, contextes
│   ├── admin.py             # routes d’administration (CRUD utilisateurs, notifications)
│   ├── auth.py              # routes d’authentification, 2FA, inscription
│   ├── forms.py             # formulaires WTForms (login, profil, règles…)
│   ├── mailer.py            # envoi d’e-mails HTML/TXT via TLS
│   ├── models.py            # modèles SQLAlchemy (User, AutomationRule, JournalEntry…)
│   ├── routes.py            # vues principales (dashboard, automation, caméra…)
│   ├── services.py          # utilitaires : notifications, avatars, purge…
│   ├── utils.py             # fonctions annexes (sauvegarde avatars, diff journal)
│   ├── static/              # assets (icônes PWA, JS, uploads)
│   └── templates/           # templates Jinja (base, emails, pages)
├── config.py                # configuration Flask (+ surcharge via .env)
├── requirements.txt         # dépendances Python
└── run.py                   # point d’entrée WSGI
```

## Gestion des utilisateurs

- Inscriptions via `/register`, comptes créés inactifs, notification e-mail en attente.
- Validation par admin ⇒ envoi automatique d’un mail d’activation.
- Désactivation ⇒ envoi de mail de suspension.
- Profil utilisateur : avatars upload/suppression, changement mot de passe avec confirmation, switch 2FA.
- Liste admin : recherche, filtres rôle/statut/2FA, tri, cartes responsive iPhone, actions avec icônes.
- Admin par défaut (`admin`) protégé de la désactivation et de la suppression.

## Sécurité & authentification forte

- Sessions sécurisées (Flask-Login), CSRF sur formulaires.
- 2FA par e-mail : code à durée limitée, option « se souvenir » (token haché).
- Badge 2FA visible sur cartes utilisateurs, pill « 2FA activé/désactivé » proche du rôle.
- Journalisation des connexions et changements (avec valeur avant/après).

## Automatisation

- Création de règles avec formulaire contextualisé.
- Cartes de règles repensées : icône, propriétaire, déclencheur/action distincts.
- Filtres rapides (texte, owner, statut), affichage responsive.
- Confirmation avant suppression, bouton « Créer une règle » masqué si journal vide post-filtre.

## Journal & notifications

- Accès strictement réservé aux admins (`is_admin`).
- Table détaillée : niveau, entité, auteur, avant/après.
- Purge filtrée par date avec modal de confirmation.
- Notifications live : toasts (succès/info/alerte), centre de notifications (cloche) avec dismiss.
- Évènements importants (activation, 2FA, erreurs) envoyés aux administrateurs.

## PWA & expérience mobile

- Installable (manifest + service worker) avec tutoriel iOS.
- Détection de mise à jour PWA et information utilisateur.
- Safe areas gérées (`--safe-area-top/bottom`), barre d’action mobile collée en bas.
- Menu latéral collapsible (icônes conservées), profil en pop-down accessible sur iPhone.
- Icônes : `img/icon-128.png` (PWA) et `img/icon-512.png` (login, splash).

## Envoi d’e-mails

- Templates HTML & texte (`app/templates/email/`).
- Palette couleur alignée UI (dégradés vert/bleu, logo `img/logo.png`).
- Types : inscription en attente, activation, désactivation, code 2FA.
- Copies de monitoring via `MAIL_MONITOR_ADDRESS`.

## Développement & bonnes pratiques

- Activer le mode debug : `FLASK_ENV=development`.
- Linter/formatteur recommandés : `ruff`, `black`.
- Compiler ponctuellement : `python -m compileall app`.
- Tests manuels : vérifier login, 2FA, création règle, purge journal, PWA install.

## Dépannage

| Problème | Solution |
|----------|----------|
| `jinja2.exceptions.TemplateNotFound` | Vérifier que les templates sont bien dans `app/templates/` et que les blueprints sont enregistrés. |
| `jinja2.exceptions.UndefinedError: 'getattr'` | Utiliser la variable globale `is_admin` fournie par `app.__init__.py`. |
| `sqlalchemy.exc.OperationalError` sur colonnes | Relancer l’app : la fonction de migration automatique ajoute les colonnes manquantes. |
| `binascii.Error: Incorrect padding` | Vérifier les pièces jointes base64 (souvent dû à un téléversement interrompu). |
| `externally-managed-environment` (macOS) | Toujours utiliser un environnement virtuel (`python -m venv .venv`). |
| Emails non envoyés | Vérifier login/pass SMTP, port TLS, whitelisting. Utiliser `MAIL_MONITOR_ADDRESS` pour audit. |

## Capteurs & relais

- **Collecte périodique** : déclenchée par APScheduler (`app/__init__.py`) selon `SENSOR_POLL_INTERVAL_MINUTES`.
- **Sondes DS18B20** : détectées via `/sys/bus/w1/devices`, stockées dans `SensorReading` (type `ds18b20`, metric `temperature`).
- **Sonde AM2315** : pilote `app/hardware/AM2315.py` utilisant `adasmbus` pour contourner les limitations SMBus sur le Pi.
- **Agrégation graphique** : réalisée dans `app/routes.py` (`dashboard`) avec calcul de min/max dynamiques et séparation des valeurs négatives (<0°C).
- **Relais** : contrôlés via `app/hardware/gpio_controller.py`, avec reconfiguration automatique du mode BCM et annotations d’état sur le graphique.
- **Infos supplémentaires** : les cartes capteurs affichent le nombre total de mesures en base et le statut de fraîcheur des dernières lectures.

## Documentation détaillée des fichiers

### Racine

- `run.py` : point d’entrée de développement ; instancie l’application et lance le serveur.
- `config.py` : configuration Flask centralisée (base de données, SMTP, capteurs, uploads).
- `requirements.txt` : dépendances Python nécessaires.
- `README.md` : document courant détaillant installation, architecture, modules.

### Package `app/`

- `app/__init__.py` : fabrique Flask, initialisation des extensions et scheduler de collecte.
- `app/routes.py` : routes principales (dashboard, paramètres, journal, API) et agrégation des données capteurs.
- `app/admin.py` : back-office utilisateurs (création/édition, notifications, journalisation).
- `app/auth.py` : routes d’authentification, inscription, gestion 2FA et journal des connexions.
- `app/models.py` : modèles SQLAlchemy (`User`, `AutomationRule`, `JournalEntry`, `SensorReading`, `Notification`, `Setting`).
- `app/forms.py` : formulaires Flask-WTF (auth, profil, paramètres, automatisation).
- `app/utils.py` : helpers transverses (avatars, détection capteurs, formatage, analyse des changements).
- `app/services.py` : création et diffusion de notifications applicatives.
- `app/tasks.py` : collecte des mesures capteurs et déclenchement du moteur d’automatisation.
- `app/automation_engine.py` : parsing/évaluation des règles et manipulation des relais.
- `app/mailer.py` : envoi SMTP des emails transactionnels (activation, code 2FA, etc.).
- `app/seed.py` : création de l’administrateur par défaut si absent.

### Matériel (`app/hardware/`)

- `AM2315.py` : pilote I²C du capteur AM2315 (température/humidité) avec gestion du bit de signe.
- `adasmbus.py` : implémentation Python de l’API SMBus utilisée par le pilote AM2315.
- `gpio_controller.py` : abstractions autour de RPi.GPIO (initialisation, lecture/écriture, détection active-low).
- `__init__.py` : documentation du package matériel.

### Templates & Frontend

- `app/templates/base.html` : layout principal (sidebar, notifications, blocs de contenu).
- `app/templates/dashboard/index.html` : tableau de bord avec cartes capteurs, carte relais et graphique ApexCharts.
- `app/templates/dashboard/journal.html` : visualisation du journal avec pagination, détails JSON et purge.
- `app/templates/dashboard/settings.html` : configuration applicative (SMTP, capteurs, scheduler).
- `app/templates/dashboard/automation.html` : gestion des règles et formulaire contextualisé.
- `app/templates/dashboard/users.html` & `user_form.html` : back-office utilisateurs (listing + modale formulaire).
- `app/templates/auth/*.html` : pages d’authentification (login, register, 2FA).
- `app/templates/email/*` : templates HTML/TXT pour les courriels transactionnels.
- `app/static/js/filters.js` : helpers front pour la recherche/filtrage dynamique.
- `app/static/js/pwa.js` & `service-worker.js` : support PWA (install, mise à jour, cache).

### Base de données & données

- `instance/dashboard.db` : base SQLite par défaut (peut être reconstruite via `flask shell`).
- `app/static/uploads/` : avatars téléversés par les utilisateurs.

## Licence

Projet privé. Adapter la section selon vos besoins avant publication publique.
