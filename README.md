# 🏠 Dashboard - Système d'automatisation domotique

Application web complète construite avec Flask pour piloter un tableau de bord d'automatisation domotique. Intègre une Progressive Web App optimisée pour iPhone, une gestion avancée des utilisateurs avec authentification à deux facteurs, un module d'automatisation intelligent, le streaming vidéo caméra, des paramètres centralisés et un journal d'audit détaillé.

![Version](https://img.shields.io/badge/version-V9--Final-blue)
![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![Flask](https://img.shields.io/badge/flask-3.0.3-green)
![License](https://img.shields.io/badge/license-Private-red)

## 📋 Table des matières

- [Fonctionnalités](#-fonctionnalités)
- [Technologies](#-technologies)
- [Prérequis](#-prérequis)
- [Installation](#-installation)
- [Configuration](#-configuration)
- [Utilisation](#-utilisation)
- [Structure du projet](#-structure-du-projet)
- [Sécurité](#-sécurité)
- [Dépannage](#-dépannage)
- [Contribution](#-contribution)

## ✨ Fonctionnalités

### 🎛️ Dashboard principal
- Vue synthétique des activités récentes avec graphiques interactifs (ApexCharts)
- Statut des capteurs en temps réel (température, humidité)
- Gestion des relais avec visualisation de l'état
- Bouton administrateur pour déclencher la collecte manuelle des capteurs
- Alertes de sécurité et notifications en temps réel

### 🔐 Gestion des utilisateurs
- Système d'inscription avec validation par administrateur
- Gestion des rôles (admin, utilisateur)
- Authentification à deux facteurs (2FA) par email
- Gestion des avatars personnalisés
- Profils utilisateurs avec modification sécurisée
- Validation d'unicité des emails et noms d'utilisateur
- Messages d'alerte visuels pour les erreurs de saisie

### 🤖 Automatisation
- Création de règles d'automatisation basées sur les capteurs
- Déclencheurs configurables (température, humidité, etc.)
- Actions sur relais (allumer, éteindre, basculer)
- Collecte planifiée des données de capteurs (configurable)
- Journalisation détaillée des actions
- Interface de gestion intuitive avec filtres et recherche

### 📊 Visualisation des données
- Graphiques interactifs avec ApexCharts
- Filtres de période (jour, semaine, mois)
- Visualisation des données de capteurs DS18B20 et AM2315
- Historique des états des relais
- Export et analyse des données

### 📹 Caméra
- Streaming vidéo USB intégré
- Interface responsive adaptée aux appareils mobiles
- Contrôles de caméra intégrés

### 📱 Progressive Web App (PWA)
- Installation sur iPhone et appareils mobiles
- Service Worker pour fonctionnement hors ligne
- Manifest optimisé pour iOS
- Interface mobile native avec barre de navigation inférieure
- Détection automatique des mises à jour

### 📧 Notifications
- Système de notifications en temps réel
- Toasts visuels avec différents niveaux (succès, avertissement, erreur)
- Centre de notifications persistant
- Alertes administrateur pour événements critiques
- Envoi d'emails pour les événements importants

### 📝 Journal d'audit
- Traçabilité complète des actions utilisateurs
- Historique des modifications (avant/après)
- Filtres par date et type d'événement
- Purge sélective des données anciennes
- Accès restreint aux administrateurs

## 🛠️ Technologies

### Backend
- **Flask** 3.0.3 - Framework web Python
- **Flask-Login** 0.6.3 - Gestion des sessions utilisateurs
- **Flask-WTF** 1.2.1 - Protection CSRF et formulaires
- **SQLAlchemy** 3.1.1 - ORM pour la base de données
- **APScheduler** 3.10.4 - Planification des tâches
- **python-dotenv** 1.0.1 - Gestion des variables d'environnement

### Frontend
- **Tailwind CSS** 3.4.17 - Framework CSS utility-first
- **ApexCharts** - Bibliothèque de graphiques interactifs
- **JavaScript vanilla** - Interactivité et PWA

### Hardware
- **w1thermsensor** 2.0.0 - Support capteurs DS18B20 (1-Wire)
- **smbus2** 0.4.3 - Communication I2C pour AM2315
- **RPi.GPIO** (optionnel) - Contrôle GPIO Raspberry Pi

### Base de données
- **SQLite** - Base de données par défaut (fichier local)
- Support pour autres bases de données via SQLAlchemy

## 📦 Prérequis

- **Python** 3.11 ou supérieur (testé sur Python 3.13)
- **pip** - Gestionnaire de paquets Python
- **Accès SMTP** - Pour l'envoi d'emails (TLS requis)
- **Outils de compilation** - Pour certaines dépendances natives
  - Linux : `build-essential`
  - macOS : Xcode Command Line Tools
  - Windows : Visual Studio Build Tools

### Optionnel (pour le matériel)
- Raspberry Pi avec GPIO
- Capteurs DS18B20 (1-Wire)
- Capteur AM2315 (I2C)
- Relais contrôlables
- Caméra USB

## 🚀 Installation

### 1. Cloner le dépôt

```bash
git clone git@github.com:patrickpinard/Dashboard.git
cd Dashboard
```

### 2. Créer un environnement virtuel

```bash
python3 -m venv .venv
source .venv/bin/activate  # Sur Windows : .venv\Scripts\activate
```

### 3. Installer les dépendances

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Installer les dépendances frontend (optionnel)

```bash
npm install
```

## ⚙️ Configuration

### Fichier `.env`

Créez un fichier `.env` à la racine du projet avec les variables suivantes :

```env
# Application Flask
FLASK_ENV=development
FLASK_SECRET_KEY=votre-clé-secrète-très-longue-et-aléatoire

# Base de données
DATABASE_URL=sqlite:///instance/dashboard.db

# Collecte des capteurs
SENSOR_POLL_INTERVAL_MINUTES=30
SENSOR_POLL_ENABLED=true

# Configuration email (SMTP)
MAIL_SERVER=smtp.example.com
MAIL_PORT=587
MAIL_USE_TLS=true
MAIL_USERNAME=votre-email@example.com
MAIL_PASSWORD=votre-mot-de-passe
MAIL_DEFAULT_SENDER="Dashboard" <votre-email@example.com>
MAIL_MONITOR_ADDRESS=monitoring@example.com
ADMIN_NOTIFICATION_EMAIL=admin@example.com

# Authentification à deux facteurs
TWOFA_CODE_LENGTH=6
TWOFA_CODE_TTL_SECONDS=300
TWOFA_RESEND_INTERVAL_SECONDS=60
TWOFA_REMEMBER_DAYS=30

# Uploads
MAX_CONTENT_LENGTH=5242880

# Matériel (optionnel)
LCD_ENABLED=true
CAMERA_DEVICE_INDEX=0
```

> **Note** : Le fichier `.env` est ignoré par Git pour des raisons de sécurité. Ne commitez jamais vos identifiants !

### Initialisation de la base de données

Créez la base de données et un compte administrateur par défaut :

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
print("✅ Base de données créée et compte admin initialisé")
PY
```

> **⚠️ Important** : Changez immédiatement le mot de passe de l'administrateur après la première connexion !

## 🎮 Utilisation

### Démarrer l'application

```bash
python run.py
```

Ou avec Flask directement :

```bash
flask --app run.py run --debug --port 8080
```

L'application sera accessible sur `http://127.0.0.1:8080`

### Accès par défaut

- **URL** : http://127.0.0.1:8080
- **Identifiant** : `admin`
- **Mot de passe** : `admin` (à changer immédiatement)

### Fonctionnalités principales

1. **Connexion** : Utilisez vos identifiants pour vous connecter
2. **2FA** : Activez l'authentification à deux facteurs dans votre profil
3. **Dashboard** : Visualisez l'état de vos capteurs et relais
4. **Automatisation** : Créez des règles pour automatiser vos équipements
5. **Capteurs** : Consultez les graphiques et historiques de vos capteurs
6. **Caméra** : Accédez au flux vidéo si une caméra est connectée

## 📁 Structure du projet

```
Dashboard/
├── app/
│   ├── __init__.py              # Initialisation Flask, blueprints, extensions
│   ├── admin.py                 # Routes administration (CRUD utilisateurs)
│   ├── auth.py                  # Authentification, 2FA, inscription
│   ├── automation_engine.py     # Moteur d'automatisation
│   ├── blueprints/
│   │   └── api.py               # API REST pour données temps réel
│   ├── constants.py              # Constantes de l'application
│   ├── forms.py                 # Formulaires WTForms
│   ├── helpers.py               # Fonctions utilitaires
│   ├── hardware/                # Pilotes matériel
│   │   ├── adasmbus.py
│   │   ├── AM2315.py
│   │   ├── gpio_controller.py
│   │   └── LCD.py
│   ├── lcd_display.py           # Gestion affichage LCD
│   ├── logging_config.py        # Configuration logging
│   ├── mailer.py                # Envoi d'emails
│   ├── models.py                # Modèles SQLAlchemy
│   ├── routes.py                # Routes principales
│   ├── seed.py                  # Initialisation données
│   ├── services.py              # Services métier
│   ├── tasks.py                 # Tâches planifiées
│   ├── utils.py                 # Utilitaires généraux
│   ├── static/                  # Assets statiques
│   │   ├── css/                 # Feuilles de style
│   │   ├── img/                 # Images et icônes
│   │   ├── js/                  # JavaScript
│   │   └── uploads/             # Uploads utilisateurs
│   └── templates/               # Templates Jinja2
│       ├── auth/                # Templates authentification
│       ├── dashboard/           # Templates dashboard
│       ├── email/               # Templates emails
│       └── errors/              # Pages d'erreur
├── instance/                    # Données instance (DB, logs)
├── logs/                        # Fichiers de logs
├── scripts/                     # Scripts utilitaires
│   ├── purge_sensor_readings.py
│   ├── restart_dashboard.sh
│   └── test_*.py               # Scripts de test matériel
├── config.py                    # Configuration Flask
├── requirements.txt             # Dépendances Python
├── package.json                 # Dépendances Node.js
├── tailwind.config.js           # Configuration Tailwind
├── run.py                       # Point d'entrée WSGI
└── README.md                    # Ce fichier
```

## 🔒 Sécurité

### Authentification
- Sessions sécurisées avec Flask-Login
- Protection CSRF sur tous les formulaires
- Authentification à deux facteurs (2FA) par email
- Gestion des appareils de confiance (30 jours)
- Validation stricte des emails et noms d'utilisateur

### Données
- Mots de passe hashés avec PBKDF2-SHA256
- Validation d'unicité des emails avant sauvegarde
- Protection contre les injections SQL (SQLAlchemy ORM)
- Limitation de taille des uploads
- Validation des types de fichiers

### Bonnes pratiques
- Variables sensibles dans `.env` (non versionnées)
- Clé secrète Flask générée aléatoirement
- Logs d'audit pour toutes les actions sensibles
- Notifications administrateur pour événements critiques

## 🐛 Dépannage

### Problèmes courants

| Problème | Solution |
|----------|----------|
| `externally-managed-environment` (macOS) | Utilisez toujours un environnement virtuel : `python3 -m venv .venv` |
| `TemplateNotFound` | Vérifiez que les templates sont dans `app/templates/` et que les blueprints sont enregistrés |
| `IntegrityError: UNIQUE constraint failed` | Vérifiez que l'email ou le nom d'utilisateur n'existe pas déjà |
| Emails non envoyés | Vérifiez les paramètres SMTP dans `.env`, le port TLS et les identifiants |
| Capteurs non détectés | Vérifiez les permissions GPIO/I2C et les connexions matérielles |
| Base de données verrouillée | Arrêtez l'application et relancez-la |

### Logs

Les logs sont disponibles dans le dossier `logs/` :
- `dashboard.log` - Logs principaux de l'application

### Mode debug

Activez le mode debug pour plus d'informations :

```bash
export FLASK_ENV=development
python run.py
```

## 📝 Notes de version

### V9-Final
- ✅ Validation d'unicité des emails avec messages d'erreur clairs
- ✅ Messages d'alerte visuels (rouge, texte blanc) pour les erreurs
- ✅ Durée d'affichage des alertes configurée à 5 secondes
- ✅ Normalisation des emails (suppression espaces, gestion valeurs vides)
- ✅ Protection contre les erreurs d'intégrité SQLite

### Versions précédentes
- V3.0-MVP : Collecte manuelle et planifiée, automatisation renforcée
- Améliorations UX mobile/desktop, palette de couleurs harmonisée

## 🤝 Contribution

Ce projet est privé. Pour toute question ou suggestion, contactez le mainteneur.

## 📄 Licence

Projet privé - Tous droits réservés

---

**Développé avec ❤️ pour l'automatisation domotique**
