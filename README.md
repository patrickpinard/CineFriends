# TemplateApp

Application Flask complète conçue comme template de base pour le développement d'applications web avec authentification utilisateur, gestion des profils, notifications et administration.

## 🚀 Fonctionnalités

- ✅ **Authentification complète** : Login, Register, 2FA, Reset Password
- ✅ **Gestion des utilisateurs** : CRUD complet avec rôles (admin/user)
- ✅ **Système de notifications** : Notifications personnelles, admin et globales
- ✅ **Progressive Web App (PWA)** : Installation sur mobile/desktop
- ✅ **Sécurité renforcée** : Rate limiting, headers de sécurité, CSRF protection
- ✅ **Logging structuré** : Logs avec contexte utilisateur et requête
- ✅ **Configuration multi-environnements** : Dev, Test, Production
- ✅ **Docker ready** : Dockerfile et docker-compose inclus

## 📋 Prérequis

- Python 3.9 ou supérieur
- pip (gestionnaire de paquets Python)
- (Optionnel) Docker et Docker Compose pour le déploiement

## 🔧 Installation

### 1. Cloner le repository

```bash
git clone <url-du-repo>
cd TemplateApp
```

### 2. Créer un environnement virtuel

```bash
python -m venv venv
source venv/bin/activate  # Sur Windows: venv\Scripts\activate
```

### 3. Installer les dépendances

```bash
pip install -r requirements.txt
```

### 4. Configuration

Créer un fichier `.env` à la racine du projet :

```bash
cp .env.example .env
```

Puis modifier les valeurs dans `.env` selon vos besoins :

```env
# Application
FLASK_SECRET_KEY=votre-clé-secrète-très-longue-et-aléatoire
FLASK_ENV=development

# Base de données (optionnel, SQLite par défaut)
DATABASE_URL=

# Email (requis pour certaines fonctionnalités)
MAIL_SERVER=smtp.example.com
MAIL_PORT=587
MAIL_USE_TLS=true
MAIL_USERNAME=votre-email@example.com
MAIL_PASSWORD=votre-mot-de-passe
MAIL_DEFAULT_SENDER="TemplateApp" <votre-email@example.com>
```

### 5. Initialiser la base de données

```bash
# Créer les migrations
flask db init

# Créer la première migration
flask db migrate -m "Initial migration"

# Appliquer les migrations
flask db upgrade
```

### 6. Lancer l'application

```bash
python run.py
```

L'application sera accessible sur `http://localhost:8080`

## 🔐 Compte par défaut

Après le premier démarrage, un compte administrateur est créé automatiquement :

- **Username** : `admin`
- **Password** : `admin`

⚠️ **Important** : Changez immédiatement le mot de passe après la première connexion !

## 🐳 Déploiement avec Docker

### Démarrage rapide

```bash
# Construire et démarrer les services
docker-compose up -d

# Voir les logs
docker-compose logs -f web

# Arrêter les services
docker-compose down
```

### Configuration Docker

Le fichier `docker-compose.yml` inclut :
- **web** : Application Flask (port 8080)
- **db** : PostgreSQL (port 5432)
- **redis** : Cache et rate limiting (port 6379)

Les variables d'environnement peuvent être définies dans `.env` ou directement dans `docker-compose.yml`.

## 🧪 Tests

### Installation des dépendances de test

```bash
pip install -r requirements-dev.txt
```

### Lancer les tests

```bash
# Tous les tests
pytest

# Avec couverture
pytest --cov=app --cov-report=html

# Tests spécifiques
pytest tests/test_auth.py -v
```

## 📁 Structure du projet

```
TemplateApp/
├── app/                    # Module principal de l'application
│   ├── __init__.py        # Initialisation Flask et configuration
│   ├── models.py          # Modèles SQLAlchemy
│   ├── auth.py            # Routes d'authentification
│   ├── admin.py           # Routes d'administration
│   ├── routes.py          # Routes principales
│   ├── forms.py           # Formulaires WTForms
│   ├── services.py        # Services (notifications)
│   ├── utils.py           # Fonctions utilitaires
│   ├── mailer.py          # Service d'envoi d'emails
│   ├── logging_config.py  # Configuration du logging
│   ├── seed.py            # Initialisation données par défaut
│   ├── templates/         # Templates Jinja2
│   └── static/            # Fichiers statiques (CSS, JS, images)
├── instance/              # Base de données SQLite (si utilisée)
├── logs/                  # Fichiers de log
├── migrations/            # Migrations Flask-Migrate
├── tests/                 # Tests unitaires
├── config.py              # Configuration de l'application
├── run.py                 # Point d'entrée
├── requirements.txt       # Dépendances Python
├── requirements-dev.txt  # Dépendances de développement
├── Dockerfile             # Image Docker
└── docker-compose.yml     # Orchestration Docker
```

## 🔒 Sécurité

### Headers de sécurité

L'application utilise Flask-Talisman pour ajouter automatiquement :
- Strict-Transport-Security (HSTS)
- Content-Security-Policy (CSP)
- X-Content-Type-Options
- X-Frame-Options
- Et autres headers de sécurité

### Rate Limiting

Protection contre les attaques par force brute :
- Login : 5 tentatives par minute
- Register : 3 tentatives par heure
- Reset Password : 3 tentatives par heure

### Authentification

- Mots de passe hashés avec PBKDF2-SHA256
- Authentification à deux facteurs (2FA) optionnelle
- Tokens sécurisés pour reset password
- Protection CSRF sur tous les formulaires

## 🛠️ Commandes utiles

### Migrations

```bash
# Créer une nouvelle migration
flask db migrate -m "Description des changements"

# Appliquer les migrations
flask db upgrade

# Revenir en arrière
flask db downgrade

# Voir l'historique
flask db history
```

### Développement

```bash
# Lancer en mode debug
FLASK_ENV=development python run.py

# Lancer avec auto-reload
flask run --reload --port 8080
```

### Commandes CLI

```bash
# Créer 10 utilisateurs de test (user1 à user10)
python3 -m flask create-test-users

# Lister tous les utilisateurs
python3 -m flask list-users

# Réinitialiser le mot de passe d'un utilisateur
python3 -m flask reset-password <username>
```

### Code Quality

```bash
# Formater le code
black app/

# Vérifier le style
flake8 app/

# Trier les imports
isort app/
```

## 📚 Documentation

- **Documentation complète** : Voir `DOCUMENTATION.md`
- **Analyse et améliorations** : Voir `ANALYSE_ET_AMELIORATIONS.md`
- **Guide d'implémentation** : Voir `README_AMELIORATIONS.md`

## 🔄 Migrations depuis une version précédente

Si vous migrez depuis une version sans Flask-Migrate :

1. Sauvegarder votre base de données existante
2. Initialiser Flask-Migrate : `flask db init`
3. Créer une migration initiale : `flask db migrate -m "Initial migration from legacy"`
4. Vérifier la migration générée
5. Appliquer : `flask db upgrade`

## 🌍 Variables d'environnement

### Application

| Variable | Description | Défaut |
|----------|-------------|--------|
| `FLASK_SECRET_KEY` | Clé secrète Flask | `change-this-secret-key` |
| `FLASK_ENV` | Environnement (development/testing/production) | `development` |
| `DEBUG` | Mode debug | `True` (dev) |

### Base de données

| Variable | Description | Défaut |
|----------|-------------|--------|
| `DATABASE_URL` | URI de la base de données | SQLite dans `instance/` |

### Email

| Variable | Description | Défaut |
|----------|-------------|--------|
| `MAIL_SERVER` | Serveur SMTP | - |
| `MAIL_PORT` | Port SMTP | `587` |
| `MAIL_USE_TLS` | Utiliser TLS | `true` |
| `MAIL_USERNAME` | Nom d'utilisateur SMTP | - |
| `MAIL_PASSWORD` | Mot de passe SMTP | - |

### Sécurité

| Variable | Description | Défaut |
|----------|-------------|--------|
| `SESSION_COOKIE_SECURE` | Cookies sécurisés (HTTPS) | `false` (dev) |
| `CORS_ORIGINS` | Origines CORS autorisées | `*` |

Voir `.env.example` pour la liste complète.

## 🐛 Dépannage

### Warning Flask-Limiter (stockage en mémoire)

**Message** : `Using the in-memory storage for tracking rate limits...`

**Explication** : En développement, Flask-Limiter utilise le stockage en mémoire par défaut. C'est normal et n'affecte pas le fonctionnement.

**En production** : Pour un stockage persistant, configurer Redis dans `.env` :
```env
RATELIMIT_STORAGE_URL=redis://localhost:6379/1
```

Puis modifier `app/__init__.py` :
```python
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"],
    storage_uri=os.getenv("RATELIMIT_STORAGE_URL", "memory://")
)
```

### Erreur de connexion à la base de données

- Vérifier que `DATABASE_URL` est correctement défini
- Vérifier les permissions du dossier `instance/`
- Pour PostgreSQL/MySQL, vérifier que le serveur est démarré

### Rate limiting trop restrictif

Modifier les limites dans `app/__init__.py` :

```python
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"]
)
```

### Erreurs de migration

```bash
# Voir l'état actuel
flask db current

# Revenir à une version précédente
flask db downgrade -1

# Forcer une nouvelle migration
flask db stamp head
flask db migrate -m "New migration"
```

## 🤝 Contribution

Ce projet est un template de base. Vous pouvez :

1. Fork le projet
2. Créer une branche pour votre fonctionnalité
3. Commiter vos changements
4. Pousser vers la branche
5. Ouvrir une Pull Request

## 📝 Licence

Ce projet est fourni comme template de base. Libre d'utilisation et de modification.

## 🙏 Remerciements

- Flask et sa communauté
- Tous les contributeurs des packages utilisés

## 📞 Support

Pour toute question ou problème :
1. Consulter la documentation (`DOCUMENTATION.md`)
2. Vérifier les issues existantes
3. Créer une nouvelle issue si nécessaire

---

**TemplateApp** - Template de base Flask pour applications web modernes

