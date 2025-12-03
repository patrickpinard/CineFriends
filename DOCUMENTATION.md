# Documentation complète de TemplateApp

## Vue d'ensemble

TemplateApp est une application Flask minimaliste conçue comme template de base pour le développement d'applications web avec authentification utilisateur, gestion des profils, notifications et administration. L'application utilise SQLite comme base de données par défaut et supporte l'authentification à deux facteurs (2FA) ainsi que la réinitialisation de mot de passe par email.

---

## Structure du projet

```
TemplateApp/
├── app/                    # Module principal de l'application
│   ├── __init__.py        # Initialisation Flask et configuration
│   ├── models.py          # Modèles SQLAlchemy (User, Setting, Notification)
│   ├── auth.py            # Routes d'authentification (login, register, 2FA, reset password)
│   ├── admin.py           # Routes d'administration (CRUD utilisateurs)
│   ├── routes.py           # Routes principales (dashboard, profil, notifications)
│   ├── forms.py            # Formulaires WTForms
│   ├── mailer.py           # Service d'envoi d'emails
│   ├── services.py         # Services (notifications)
│   ├── utils.py            # Fonctions utilitaires
│   ├── logging_config.py   # Configuration du logging structuré
│   ├── seed.py             # Initialisation données par défaut
│   ├── templates/          # Templates Jinja2
│   └── static/             # Fichiers statiques (CSS, JS, images)
├── config.py               # Configuration de l'application
├── run.py                  # Point d'entrée de l'application
└── requirements.txt        # Dépendances Python
```

---

## Documentation détaillée par fichier

### 1. `app/__init__.py`

**Rôle** : Point d'initialisation principal de l'application Flask.

**Fonctionnalités principales** :

- **`create_app()`** : Factory function qui crée et configure l'instance Flask
  - Initialise les extensions (SQLAlchemy, LoginManager, CSRFProtect, CORS)
  - Configure la base de données SQLite avec gestion des chemins absolus
  - Vérifie les permissions d'écriture sur le répertoire de la base de données
  - Teste la connexion SQLite avant l'initialisation complète
  - Enregistre les blueprints (auth, main, admin)
  - Configure les filtres Jinja2 personnalisés (`local_datetime`)
  - Ajoute des variables globales au contexte Jinja2 (notifications, année courante, statut admin)
  - Implémente un système de génération de palettes de couleurs pour les avatars
  - Gère les migrations automatiques de la base de données (ajout de colonnes manquantes)

**Migrations automatiques** :
- Ajoute automatiquement les colonnes manquantes dans les tables `user` et `notification`
- Supporte les migrations pour : `last_login`, `avatar_filename`, `twofa_*`, `address`, `street`, `postal_code`, `city`, `country`, `phone`, `first_name`, `last_name`, `title`, `reset_token_hash`, `reset_token_expires`, `persistent`

**Variables globales Jinja2** :
- `header_notifications` : Liste des 10 dernières notifications de l'utilisateur
- `header_unread_notifications` : Nombre de notifications non lues
- `current_year` : Année courante
- `is_admin` : Booléen indiquant si l'utilisateur est administrateur
- `avatar_palette(name)` : Fonction générant une palette de couleurs pour les avatars

---

### 2. `app/models.py`

**Rôle** : Définit les modèles de données SQLAlchemy pour l'application.

#### **Classe `User`**

**Description** : Modèle représentant un utilisateur du système. Hérite de `UserMixin` pour la compatibilité avec Flask-Login.

**Attributs** :
- `id` (int) : Identifiant unique (clé primaire)
- `title` (str) : Civilité (Monsieur/Madame), optionnel
- `first_name` (str) : Prénom, optionnel
- `last_name` (str) : Nom de famille, optionnel
- `username` (str) : Nom d'utilisateur unique, requis
- `email` (str) : Adresse email unique, optionnelle
- `role` (str) : Rôle ('admin' ou 'user'), défaut: 'user'
- `password_hash` (str) : Hash du mot de passe (PBKDF2-SHA256), requis
- `active` (bool) : Statut actif/inactif, défaut: True
- `created_at` (datetime) : Date de création du compte
- `last_login` (datetime) : Date de dernière connexion, optionnel
- `avatar_filename` (str) : Nom du fichier avatar, optionnel
- `address` (str) : Ancien champ d'adresse (compatibilité)
- `street` (str) : Rue, optionnel
- `postal_code` (str) : Code postal, optionnel
- `city_country` (str) : Ancien champ ville/pays (compatibilité)
- `city` (str) : Ville, optionnel
- `country` (str) : Pays, optionnel
- `phone` (str) : Téléphone, optionnel
- `twofa_enabled` (bool) : 2FA activée, défaut: False
- `twofa_code_hash` (str) : Hash du code 2FA, optionnel
- `twofa_code_sent_at` (datetime) : Date d'envoi du code 2FA, optionnel
- `twofa_trusted_token_hash` (str) : Hash du token de confiance 2FA, optionnel
- `twofa_trusted_created_at` (datetime) : Date de création du token de confiance, optionnel
- `reset_token_hash` (str) : Hash du token de réinitialisation, optionnel
- `reset_token_expires` (datetime) : Date d'expiration du token de réinitialisation, optionnel

**Méthodes** :
- `set_password(password: str)` : Hash et définit le mot de passe avec PBKDF2-SHA256
- `check_password(password: str)` : Vérifie si le mot de passe correspond au hash
- `is_active()` : Retourne le statut actif du compte (requis par Flask-Login)

**Relations** :
- `notifications` : Relation one-to-many vers les notifications de l'utilisateur

#### **Classe `Setting`**

**Description** : Modèle pour stocker des paramètres de configuration dynamiques.

**Attributs** :
- `id` (int) : Identifiant unique (clé primaire)
- `key` (str) : Clé unique du paramètre, requis
- `value` (str) : Valeur du paramètre, optionnelle
- `updated_at` (datetime) : Date de dernière mise à jour

#### **Classe `Notification`**

**Description** : Modèle pour les notifications utilisateurs affichées dans l'interface.

**Attributs** :
- `id` (int) : Identifiant unique (clé primaire)
- `user_id` (int) : ID de l'utilisateur destinataire (FK vers User), optionnel
- `audience` (str) : Audience ('user', 'admin', 'global'), défaut: 'user'
- `level` (str) : Niveau ('info', 'warning', 'error'), défaut: 'info'
- `title` (str) : Titre de la notification, requis
- `message` (str) : Message de la notification, requis
- `action_url` (str) : URL d'action associée, optionnelle
- `created_at` (datetime) : Date de création
- `read` (bool) : Notification lue/non lue, défaut: False
- `persistent` (bool) : Notification persistante, défaut: False

**Relations** :
- `user` : Relation many-to-one vers User

#### **Fonction `load_user(user_id: str)`**

**Description** : Callback Flask-Login pour charger un utilisateur depuis la base de données.

---

### 3. `app/auth.py`

**Rôle** : Gère toutes les routes d'authentification et de gestion de session.

**Blueprint** : `auth_bp` avec préfixe `/auth`

#### **Routes** :

1. **`/auth/login` (GET, POST)**
   - **Fonction** : `login()`
   - **Description** : Page de connexion
   - **Fonctionnalités** :
     - Redirige les utilisateurs déjà connectés vers le dashboard
     - Valide les identifiants (username/password)
     - Vérifie si le compte est actif
     - Gère l'authentification 2FA avec token de confiance (si activée)
     - Envoie un code 2FA par email si nécessaire
     - Met à jour `last_login` lors de la connexion réussie
     - Nettoie les espaces dans le username avant validation

2. **`/auth/logout` (GET)**
   - **Fonction** : `logout()`
   - **Description** : Déconnexion de l'utilisateur
   - **Fonctionnalités** :
     - Nettoie la session (supprime les données 2FA)
     - Déconnecte l'utilisateur via Flask-Login
     - Redirige vers la page de connexion

3. **`/auth/register` (GET, POST)**
   - **Fonction** : `register()`
   - **Description** : Inscription d'un nouvel utilisateur
   - **Fonctionnalités** :
     - Vérifie l'unicité du username et de l'email
     - Crée un compte avec statut `active=False` (nécessite approbation admin)
     - Envoie un email de confirmation à l'utilisateur
     - Envoie une notification aux administrateurs
     - Redirige vers la page d'attente d'approbation

4. **`/auth/inscription-en-attente` (GET)**
   - **Fonction** : `registration_pending()`
   - **Description** : Page d'information après inscription
   - **Fonctionnalités** :
     - Affiche un message informant que la demande est en attente
     - Indique si un email a été envoyé et à quelle adresse

5. **`/auth/2fa` (GET, POST)**
   - **Fonction** : `twofa_verify()`
   - **Description** : Vérification du code 2FA
   - **Fonctionnalités** :
     - Vérifie que l'utilisateur est en session 2FA
     - Valide le code 2FA (vérifie expiration et correspondance)
     - Gère l'option "Mémoriser cet appareil" (crée un token de confiance)
     - Supprime le token de confiance si l'utilisateur choisit de ne plus faire confiance
     - Connecte l'utilisateur après validation réussie
     - Gère le renvoi de code avec intervalle minimum

6. **`/auth/reset-password` (GET, POST)**
   - **Fonction** : `reset_password_request()`
   - **Description** : Demande de réinitialisation de mot de passe
   - **Fonctionnalités** :
     - Accepte une adresse email
     - Génère un token sécurisé valide 1 heure
     - Envoie un email avec le lien de réinitialisation
     - Protège contre l'énumération d'emails (même message si email existe ou non)

7. **`/auth/reset-password/<token>` (GET, POST)**
   - **Fonction** : `reset_password(token: str)`
   - **Description** : Réinitialisation du mot de passe avec token
   - **Fonctionnalités** :
     - Valide le token (vérifie existence, expiration, correspondance)
     - Permet la réinitialisation même si l'utilisateur est connecté
     - Adapte le message selon le contexte (utilisateur connecté ou non)
     - Met à jour le mot de passe et supprime le token après utilisation

#### **Fonctions internes** :

- **`_issue_twofa_code(user: User)`** : Génère et envoie un code 2FA par email

---

### 4. `app/admin.py`

**Rôle** : Gère toutes les routes d'administration (CRUD utilisateurs).

**Blueprint** : `admin_bp` avec préfixe `/admin`

**Protection** : Toutes les routes nécessitent l'authentification et le rôle admin

#### **Routes** :

1. **`/admin/utilisateurs` (GET)**
   - **Fonction** : `users()`
   - **Description** : Liste des utilisateurs avec filtres et recherche
   - **Fonctionnalités** :
     - Recherche par username ou email
     - Filtre par rôle (admin/user)
     - Filtre par statut (actif/inactif)
     - Tri par nom ou date de création
     - Pagination implicite (affiche tous les résultats)

2. **`/admin/utilisateurs/nouveau` (GET, POST)**
   - **Fonction** : `create_user()`
   - **Description** : Création d'un nouvel utilisateur
   - **Fonctionnalités** :
     - Valide l'unicité du username et de l'email
     - Vérifie que l'email est fourni si 2FA est activée
     - Crée le compte avec mot de passe hashé
     - Gère l'upload d'avatar
     - Envoie une notification à l'utilisateur créé
     - Notifie les administrateurs de la création

3. **`/admin/utilisateurs/<user_id>/modifier` (GET, POST)**
   - **Fonction** : `edit_user(user_id: int)`
   - **Description** : Modification d'un utilisateur existant
   - **Fonctionnalités** :
     - Valide l'unicité du username et de l'email (si modifiés)
     - Protège le compte "admin" (ne peut pas être désactivé)
     - Gère la modification du mot de passe (optionnel)
     - Gère l'upload/suppression d'avatar
     - Détecte les changements d'état (actif/inactif, 2FA)
     - Envoie des emails lors de l'activation/désactivation
     - Crée des notifications pour les changements importants
     - Notifie les administrateurs des modifications

4. **`/admin/utilisateurs/<user_id>/supprimer` (POST)**
   - **Fonction** : `delete_user(user_id: int)`
   - **Description** : Suppression d'un utilisateur
   - **Fonctionnalités** :
     - Protège le compte "admin" (ne peut pas être supprimé)
     - Supprime l'avatar de l'utilisateur
     - Supprime l'utilisateur de la base de données
     - Notifie les administrateurs de la suppression

#### **Fonctions utilitaires** :

- **`_require_admin()`** : Vérifie que l'utilisateur actuel est administrateur

---

### 5. `app/routes.py`

**Rôle** : Gère les routes principales de l'application (dashboard, profil, notifications, PWA).

**Blueprint** : `main_bp` sans préfixe

#### **Routes** :

1. **`/` (GET)**
   - **Fonction** : `dashboard()`
   - **Description** : Page d'accueil vide (template de base)

2. **`/graphiques` (GET)**
   - **Fonction** : `charts()`
   - **Description** : Page graphiques vide

3. **`/automatisation` (GET)**
   - **Fonction** : `automation()`
   - **Description** : Page automatisation vide

4. **`/camera` (GET)**
   - **Fonction** : `camera()`
   - **Description** : Page caméra vide

5. **`/parametres` (GET)**
   - **Fonction** : `settings()`
   - **Description** : Page paramètres vide

6. **`/journal` (GET)**
   - **Fonction** : `journal()`
   - **Description** : Page journal vide

7. **`/affichage-lcd` (GET)**
   - **Fonction** : `lcd_preview()`
   - **Description** : Page affichage LCD vide

8. **`/profil` (GET, POST)**
   - **Fonction** : `profile()`
   - **Description** : Gestion du profil utilisateur
   - **Fonctionnalités** :
     - Affiche les informations du profil
     - Permet la modification des informations personnelles
     - Gère le changement de mot de passe (optionnel)
     - Gère l'upload/suppression d'avatar
     - Active/désactive la 2FA
     - Valide l'unicité du username et de l'email
     - Vérifie que l'email est fourni pour activer la 2FA

9. **`/notifications/read` (POST)**
   - **Fonction** : `notifications_mark_read()`
   - **Description** : Marque les notifications comme lues
   - **Fonctionnalités** :
     - Accepte une liste d'IDs de notifications (optionnel)
     - Marque toutes les notifications de l'utilisateur si aucun ID fourni
     - Respecte les audiences (user, admin, global)

10. **`/notifications/clear` (POST)**
    - **Fonction** : `notifications_clear()`
    - **Description** : Supprime les notifications
    - **Fonctionnalités** :
      - Accepte une liste d'IDs de notifications (optionnel)
      - Supprime les notifications personnelles
      - Marque comme lues les notifications globales/admin (ne peut pas les supprimer)
      - Respecte les audiences

11. **`/icon/<int:size>.png` (GET)**
    - **Fonction** : `generate_icon(size: int)`
    - **Description** : Génère une icône PWA avec fond blanc
    - **Fonctionnalités** :
      - Utilise PIL pour générer des icônes dynamiques
      - Centre le logo sur un fond blanc
      - Gère la transparence du logo
      - Cache les icônes générées (1 an)
      - Fallback vers le logo original si PIL indisponible

12. **`/manifest.json` (GET)**
    - **Fonction** : `manifest()`
    - **Description** : Manifest PWA
    - **Fonctionnalités** :
      - Retourne le manifest JSON pour l'installation PWA
      - Inclut les icônes générées dynamiquement

13. **`/api/server-time` (GET)**
    - **Fonction** : `server_time()`
    - **Description** : API retournant l'heure du serveur
    - **Fonctionnalités** :
      - Retourne l'heure locale et UTC
      - Inclut l'offset de timezone
      - Format ISO et format lisible

14. **`/service-worker.js` (GET)**
    - **Fonction** : `service_worker()`
    - **Description** : Service worker pour PWA
    - **Fonctionnalités** :
      - Sert le fichier service-worker.js
      - Désactive le cache pour toujours servir la dernière version

#### **Gestionnaires d'erreurs** :

- **`not_found(error)`** : Gère les erreurs 404
- **`internal_error(error)`** : Gère les erreurs 500 (rollback DB)

#### **Cache** :

- **`_settings_cache`** : Cache des paramètres système (non utilisé actuellement)
- **`invalidate_settings_cache()`** : Invalide le cache des paramètres

---

### 6. `app/forms.py`

**Rôle** : Définit tous les formulaires WTForms utilisés dans l'application.

#### **Formulaires** :

1. **`LoginForm`**
   - **Champs** :
     - `username` : Nom d'utilisateur (requis, 3-80 caractères)
     - `password` : Mot de passe (requis, 4-128 caractères)
     - `submit` : Bouton de soumission

2. **`UserForm`**
   - **Usage** : Création/modification d'utilisateur par admin
   - **Champs** :
     - `title` : Civilité (optionnel)
     - `first_name` : Prénom (optionnel, max 100)
     - `last_name` : Nom (optionnel, max 100)
     - `username` : Nom d'utilisateur (requis, 3-80 caractères)
     - `email` : Email (optionnel, format email valide, max 120)
     - `role` : Rôle (admin/user)
     - `password` : Mot de passe (optionnel, 4-128 caractères)
     - `confirm_password` : Confirmation (doit correspondre)
     - `active` : Statut actif (booléen)
     - `avatar` : Upload d'avatar (jpg, jpeg, png, gif)
     - `remove_avatar` : Supprimer l'avatar actuel
     - `street` : Rue (optionnel, max 255)
     - `postal_code` : Code postal (optionnel, max 20)
     - `city` : Ville (optionnel, max 255)
     - `country` : Pays (optionnel, max 255)
     - `phone` : Téléphone (optionnel, max 50)
     - `twofa_enabled` : Activer 2FA (booléen)
     - `submit` : Bouton de soumission

3. **`ProfileForm`**
   - **Usage** : Modification du profil par l'utilisateur
   - **Champs** : Similaires à `UserForm` mais sans `role` et `active`

4. **`RegisterForm`**
   - **Usage** : Inscription d'un nouvel utilisateur
   - **Champs** :
     - `username` : Nom d'utilisateur (requis, 3-80 caractères)
     - `email` : Email (requis, format email valide, max 120)
     - `password` : Mot de passe (requis, 4-128 caractères)
     - `confirm_password` : Confirmation (requis, doit correspondre)
     - `submit` : Bouton de soumission

5. **`TwoFactorForm`**
   - **Usage** : Vérification du code 2FA
   - **Champs** :
     - `code` : Code de vérification (requis, 6 chiffres)
     - `remember_device` : Mémoriser cet appareil (booléen)
     - `submit` : Bouton de soumission

6. **`ResetPasswordRequestForm`**
   - **Usage** : Demande de réinitialisation de mot de passe
   - **Champs** :
     - `email` : Email (requis, format email valide, max 120)
     - `submit` : Bouton de soumission

7. **`ResetPasswordForm`**
   - **Usage** : Réinitialisation du mot de passe avec token
   - **Champs** :
     - `password` : Nouveau mot de passe (requis, 4-128 caractères)
     - `confirm_password` : Confirmation (requis, doit correspondre)
     - `submit` : Bouton de soumission

---

### 7. `app/mailer.py`

**Rôle** : Service d'envoi d'emails via SMTP.

#### **Fonction `send_email()`**

**Signature** :
```python
def send_email(
    subject: str,
    recipients: str | Iterable[str],
    body: str,
    html_body: str | None = None,
    bcc: Sequence[str] | None = None,
) -> bool
```

**Description** : Envoie un email via SMTP avec support TLS/SSL.

**Paramètres** :
- `subject` : Sujet de l'email
- `recipients` : Destinataire(s) (string ou liste)
- `body` : Corps texte de l'email
- `html_body` : Corps HTML de l'email (optionnel)
- `bcc` : Destinataires en copie cachée (optionnel)

**Retour** : `True` si l'email a été envoyé avec succès, `False` sinon

**Fonctionnalités** :
- Lit la configuration SMTP depuis `app.config`
- Supporte TLS et SSL
- Ajoute automatiquement `MAIL_MONITOR_ADDRESS` en BCC si configuré
- Gère les erreurs avec logging détaillé
- Retourne un booléen pour indiquer le succès/échec

**Configuration requise** :
- `MAIL_SERVER` : Serveur SMTP
- `MAIL_PORT` : Port SMTP (défaut: 587)
- `MAIL_USERNAME` : Nom d'utilisateur SMTP
- `MAIL_PASSWORD` : Mot de passe SMTP
- `MAIL_DEFAULT_SENDER` : Expéditeur par défaut
- `MAIL_USE_TLS` : Utiliser TLS (défaut: true)
- `MAIL_USE_SSL` : Utiliser SSL (défaut: false)
- `MAIL_MONITOR_ADDRESS` : Adresse de monitoring (optionnel)

---

### 8. `app/services.py`

**Rôle** : Services utilitaires pour les notifications.

#### **Fonction `create_notification()`**

**Signature** :
```python
def create_notification(
    *,
    title: str,
    message: str,
    level: str = "info",
    user: User | None = None,
    audience: str = "user",
    action_endpoint: str | None = None,
    action_kwargs: dict | None = None,
    persistent: bool = False,
) -> Notification
```

**Description** : Crée une notification dans la base de données.

**Paramètres** :
- `title` : Titre de la notification
- `message` : Message de la notification
- `level` : Niveau ('info', 'warning', 'error'), défaut: 'info'
- `user` : Utilisateur destinataire (optionnel)
- `audience` : Audience ('user', 'admin', 'global'), défaut: 'user'
- `action_endpoint` : Endpoint Flask pour l'action (optionnel)
- `action_kwargs` : Arguments pour l'URL d'action (optionnel)
- `persistent` : Notification persistante, défaut: False

**Retour** : Instance `Notification` créée

#### **Fonction `notify_admins()`**

**Signature** :
```python
def notify_admins(
    *,
    title: str,
    message: str,
    level: str = "info",
    action_endpoint: str | None = None,
    action_kwargs: dict | None = None,
    persistent: bool = True,
) -> Notification
```

**Description** : Crée une notification adressée à tous les administrateurs.

**Paramètres** : Similaires à `create_notification()` mais avec `audience="admin"` et `persistent=True` par défaut

**Retour** : Instance `Notification` créée

---

### 9. `app/utils.py`

**Rôle** : Fonctions utilitaires diverses.

#### **Fonctions** :

1. **`utc_to_local(utc_dt: datetime) -> datetime`**
   - **Description** : Convertit un datetime UTC en datetime local
   - **Fonctionnalités** :
     - Calcule l'offset entre UTC et l'heure locale du système
     - Prend en compte l'heure d'été/hiver automatiquement
     - Gère les valeurs None

2. **`format_local_datetime(dt: datetime, format_str: str = "%d/%m/%Y %H:%M") -> str`**
   - **Description** : Formate un datetime UTC en heure locale
   - **Paramètres** :
     - `dt` : Datetime UTC à convertir
     - `format_str` : Format de sortie (défaut: "%d/%m/%Y %H:%M")
   - **Retour** : Chaîne formatée ou chaîne vide si None

3. **`save_avatar(file: FileStorage) -> str`**
   - **Description** : Sauvegarde un fichier avatar uploadé
   - **Fonctionnalités** :
     - Génère un nom de fichier unique avec token aléatoire
     - Conserve l'extension originale
     - Crée le répertoire d'upload si nécessaire
   - **Retour** : Nom du fichier sauvegardé

4. **`delete_avatar(filename: str | None) -> None`**
   - **Description** : Supprime un fichier avatar
   - **Fonctionnalités** :
     - Vérifie l'existence du fichier avant suppression
     - Log les erreurs sans interrompre l'exécution

5. **`serialize_value(value)`**
   - **Description** : Sérialise une valeur Python en format JSON-compatible
   - **Fonctionnalités** :
     - Convertit datetime/date en ISO format
     - Gère les booléens et None
     - Convertit le reste en string

6. **`build_changes(original: dict, updated: dict, fields: list[str]) -> dict`**
   - **Description** : Construit un dictionnaire des changements entre deux dictionnaires
   - **Paramètres** :
     - `original` : Dictionnaire avec valeurs originales
     - `updated` : Dictionnaire avec valeurs mises à jour
     - `fields` : Liste des champs à comparer
   - **Retour** : Dictionnaire avec champs modifiés (`before`/`after`)

---

### 10. `app/logging_config.py`

**Rôle** : Configuration du logging structuré pour l'application.

#### **Classe `StructuredLogger`**

**Description** : Logger personnalisé qui ajoute un contexte structuré aux logs.

**Méthodes** :
- `debug(message: str, **kwargs)` : Log debug avec contexte
- `info(message: str, **kwargs)` : Log info avec contexte
- `warning(message: str, **kwargs)` : Log warning avec contexte
- `error(message: str, **kwargs)` : Log error avec contexte
- `exception(message: str, **kwargs)` : Log exception avec traceback et contexte

**Contexte automatique** :
- Timestamp UTC
- Informations de requête (method, path, endpoint, remote_addr) si disponible
- Informations utilisateur (id, username, role) si authentifié
- Contexte personnalisé via `**kwargs`

#### **Fonctions** :

1. **`get_logger(name: Optional[str] = None) -> StructuredLogger`**
   - **Description** : Récupère un logger structuré
   - **Paramètres** :
     - `name` : Nom du logger (optionnel, utilise le nom du module appelant par défaut)
   - **Retour** : Instance de `StructuredLogger`

2. **`get_app_logger() -> StructuredLogger`**
   - **Description** : Récupère le logger de l'application Flask actuelle
   - **Fonctionnalités** :
     - Utilise `current_app.logger` si disponible
     - Fallback vers un logger générique si pas de contexte de requête
   - **Retour** : Instance de `StructuredLogger`

**Format des logs** :
Les logs sont formatés en JSON pour faciliter le parsing et l'analyse :
```
Message | Context: {"timestamp": "...", "request": {...}, "user": {...}, ...}
```

---

### 11. `app/seed.py`

**Rôle** : Initialisation des données par défaut.

#### **Fonction `ensure_default_admin()`**

**Description** : Crée un compte administrateur par défaut si aucun n'existe.

**Fonctionnalités** :
- Vérifie l'existence d'un utilisateur avec username "admin"
- Crée un compte admin avec :
  - Username : "admin"
  - Password : "admin" (à changer immédiatement)
  - Role : "admin"
  - Active : True

**Appel** : Automatiquement lors de l'initialisation de l'application dans `app/__init__.py`

---

### 12. `config.py`

**Rôle** : Configuration centralisée de l'application.

#### **Classe `Config`**

**Description** : Classe de configuration Flask chargée depuis les variables d'environnement.

**Configuration** :

- **Base de données** :
  - `SQLALCHEMY_DATABASE_URI` : URI de la base de données (défaut: `instance/database.db`)
  - `SQLALCHEMY_TRACK_MODIFICATIONS` : False

- **Sécurité** :
  - `SECRET_KEY` : Clé secrète Flask (depuis `FLASK_SECRET_KEY` ou défaut)
  - `WTF_CSRF_TIME_LIMIT` : None (pas de limite de temps)
  - `SESSION_COOKIE_SECURE` : False (dev)
  - `REMEMBER_COOKIE_SECURE` : False (dev)
  - `PREFERRED_URL_SCHEME` : "https"

- **Uploads** :
  - `UPLOAD_FOLDER` : `app/static/uploads`
  - `MAX_CONTENT_LENGTH` : 5 MB (depuis `MAX_CONTENT_LENGTH`)

- **2FA** :
  - `TWOFA_CODE_LENGTH` : 6 (depuis `TWOFA_CODE_LENGTH`)
  - `TWOFA_CODE_TTL_SECONDS` : 300 (5 minutes, depuis `TWOFA_CODE_TTL_SECONDS`)
  - `TWOFA_RESEND_INTERVAL_SECONDS` : 60 (depuis `TWOFA_RESEND_INTERVAL_SECONDS`)
  - `TWOFA_REMEMBER_DAYS` : 30 (depuis `TWOFA_REMEMBER_DAYS`)
  - `TWOFA_REMEMBER_COOKIE` : "templateapp_trusted_device" (depuis `TWOFA_REMEMBER_COOKIE`)

- **Email** :
  - `MAIL_SERVER` : Serveur SMTP (depuis `MAIL_SERVER`)
  - `MAIL_PORT` : 587 (depuis `MAIL_PORT`)
  - `MAIL_USE_TLS` : True (depuis `MAIL_USE_TLS`)
  - `MAIL_USE_SSL` : False (depuis `MAIL_USE_SSL`)
  - `MAIL_USERNAME` : Nom d'utilisateur SMTP (depuis `MAIL_USERNAME`)
  - `MAIL_PASSWORD` : Mot de passe SMTP (depuis `MAIL_PASSWORD`)
  - `MAIL_DEFAULT_SENDER` : Expéditeur par défaut (depuis `MAIL_DEFAULT_SENDER` ou `MAIL_USERNAME`)
  - `ADMIN_NOTIFICATION_EMAIL` : Email pour notifications admin (depuis `ADMIN_NOTIFICATION_EMAIL`)
  - `MAIL_MONITOR_ADDRESS` : Adresse de monitoring (depuis `MAIL_MONITOR_ADDRESS`)

**Gestion de la base de données** :
- Crée automatiquement le répertoire `instance/` si nécessaire
- Vérifie les permissions d'écriture
- Utilise un chemin absolu avec 4 slashes pour SQLite

---

### 13. `run.py`

**Rôle** : Point d'entrée de l'application.

**Fonctionnalités** :
- Importe et crée l'application Flask via `create_app()`
- Lance le serveur de développement Flask
- Configuration :
  - Host : `0.0.0.0` (accessible depuis toutes les interfaces)
  - Port : `8080`
  - Debug : `True`

**Usage** :
```bash
python run.py
```

---

## Templates

### Structure des templates

Les templates sont organisés en plusieurs dossiers :

- **`app/templates/auth/`** : Templates d'authentification
  - `base.html` : Template de base pour les pages d'authentification
  - `login.html` : Page de connexion
  - `register.html` : Page d'inscription
  - `registration_pending.html` : Page d'attente d'approbation
  - `reset_password_request.html` : Page de demande de réinitialisation
  - `reset_password.html` : Page de réinitialisation avec token
  - `twofa.html` : Page de vérification 2FA

- **`app/templates/dashboard/`** : Templates du tableau de bord
  - `base.html` : Template de base avec sidebar et navigation
  - `index.html` : Page d'accueil vide
  - `profile.html` : Page de profil utilisateur
  - `users.html` : Liste des utilisateurs (admin)
  - `user_form.html` : Formulaire création/modification utilisateur (admin)
  - Pages vides : `charts.html`, `automation.html`, `camera.html`, `settings.html`, `journal.html`, `lcd_preview.html`

- **`app/templates/email/`** : Templates d'emails
  - Templates HTML et texte pour chaque type d'email
  - `account_approved.html/txt` : Email d'activation de compte
  - `account_deactivated.html/txt` : Email de désactivation
  - `registration_pending.html/txt` : Email de confirmation d'inscription
  - `reset_password.html/txt` : Email de réinitialisation de mot de passe
  - `twofa_code.html/txt` : Email avec code 2FA

- **`app/templates/errors/`** : Templates d'erreurs
  - `404.html` : Page d'erreur 404
  - `500.html` : Page d'erreur 500

### Caractéristiques des templates

- **Design** : Utilise Tailwind CSS pour le styling
- **Responsive** : Design adaptatif mobile/desktop
- **PWA** : Support Progressive Web App avec manifest et service worker
- **Branding** : Logo uniforme dans tous les emails et pages
- **Couleurs** : Palette de couleurs cohérente (teal pour les boutons principaux)

---

## Fichiers statiques

### Structure

- **`app/static/css/`** : Feuilles de style
  - `input.css` : Input Tailwind CSS
  - `main.css` : Styles personnalisés

- **`app/static/js/`** : Scripts JavaScript
  - `main.js` : Scripts principaux
  - `pwa.js` : Scripts PWA
  - `service-worker.js` : Service worker pour PWA
  - `filters.js` : Filtres JavaScript

- **`app/static/img/`** : Images
  - `logo.png` : Logo de l'application
  - Icônes PWA de différentes tailles (16x16 à 1024x1024)

- **`app/static/uploads/`** : Uploads utilisateurs
  - Avatars des utilisateurs

---

## Sécurité

### Authentification

- **Mots de passe** : Hashés avec PBKDF2-SHA256 (via Werkzeug)
- **Sessions** : Gérées par Flask-Login
- **CSRF** : Protection CSRF activée sur tous les formulaires (Flask-WTF)
- **2FA** : Authentification à deux facteurs optionnelle avec codes à 6 chiffres
- **Tokens** : Tokens de réinitialisation de mot de passe sécurisés avec expiration

### Protection des routes

- **`@login_required`** : Décorateur Flask-Login pour protéger les routes
- **`_require_admin()`** : Vérification du rôle admin pour les routes d'administration
- **`@admin_bp.before_request`** : Hook global pour vérifier les droits admin

### Validation

- **Formulaires** : Validation côté serveur avec WTForms
- **Email** : Validation du format email
- **Mots de passe** : Longueur minimale de 4 caractères
- **Usernames** : Longueur minimale de 3 caractères, unicité vérifiée

---

## Base de données

### Modèle de données

- **User** : Table principale des utilisateurs
- **Setting** : Table des paramètres système
- **Notification** : Table des notifications utilisateurs

### Migrations

- Migrations automatiques lors du démarrage de l'application
- Ajout automatique des colonnes manquantes
- Compatible avec les bases de données existantes

### Fichier de base de données

- **Emplacement par défaut** : `instance/database.db`
- **Format** : SQLite
- **Création** : Automatique au premier démarrage

---

## Emails

### Types d'emails envoyés

1. **Confirmation d'inscription** : Envoyé après l'inscription
2. **Activation de compte** : Envoyé quand un admin active un compte
3. **Désactivation de compte** : Envoyé quand un admin désactive un compte
4. **Code 2FA** : Envoyé lors de la connexion avec 2FA activée
5. **Réinitialisation de mot de passe** : Envoyé avec le lien de réinitialisation

### Caractéristiques des emails

- **Format** : HTML et texte (multipart)
- **Logo** : Logo uniforme dans tous les emails
- **Couleurs** : Boutons avec couleur teal uniforme (#14b8a6)
- **Formulation** : Professionnelle et cohérente
- **Footer** : Copyright et mention automatique

---

## Fonctionnalités principales

### Authentification

- ✅ Connexion avec username/password
- ✅ Inscription avec approbation admin
- ✅ Authentification à deux facteurs (2FA)
- ✅ Réinitialisation de mot de passe par email
- ✅ Mémorisation d'appareil pour 2FA (30 jours)
- ✅ Gestion des sessions

### Gestion des utilisateurs

- ✅ CRUD complet des utilisateurs (admin)
- ✅ Gestion des profils utilisateurs
- ✅ Upload/suppression d'avatars
- ✅ Activation/désactivation de comptes
- ✅ Gestion des rôles (admin/user)

### Notifications

- ✅ Système de notifications intégré
- ✅ Notifications par utilisateur, admin ou globales
- ✅ Notifications persistantes
- ✅ Marquer comme lues / Supprimer

### PWA

- ✅ Manifest PWA
- ✅ Service Worker
- ✅ Installation sur mobile/desktop
- ✅ Icônes générées dynamiquement

---

## Configuration requise

### Python

- **Version** : Python 3.9 ou supérieur
- **Packages** : Voir `requirements.txt`

### Variables d'environnement

Créer un fichier `.env` à la racine avec :

```env
# Application
FLASK_SECRET_KEY=votre-clé-secrète-très-longue-et-aléatoire

# Base de données (optionnel)
DATABASE_URL=sqlite:///instance/database.db

# Email (requis pour l'envoi d'emails)
MAIL_SERVER=smtp.example.com
MAIL_PORT=587
MAIL_USE_TLS=true
MAIL_USERNAME=votre-email@example.com
MAIL_PASSWORD=votre-mot-de-passe
MAIL_DEFAULT_SENDER="TemplateApp" <votre-email@example.com>
MAIL_MONITOR_ADDRESS=monitoring@example.com
ADMIN_NOTIFICATION_EMAIL=admin@example.com

# 2FA (optionnel)
TWOFA_CODE_LENGTH=6
TWOFA_CODE_TTL_SECONDS=300
TWOFA_RESEND_INTERVAL_SECONDS=60
TWOFA_REMEMBER_DAYS=30
TWOFA_REMEMBER_COOKIE=templateapp_trusted_device

# Uploads (optionnel)
MAX_CONTENT_LENGTH=5242880
```

---

## Installation et démarrage

### 1. Installation des dépendances

```bash
pip install -r requirements.txt
```

### 2. Configuration

Créer le fichier `.env` avec les variables nécessaires (voir ci-dessus).

### 3. Démarrage

```bash
python run.py
```

L'application sera accessible sur `http://localhost:8080`

### 4. Compte par défaut

- **Username** : `admin`
- **Password** : `admin`

⚠️ **Important** : Changer immédiatement le mot de passe après la première connexion !

---

## Dépendances principales

- **Flask** : Framework web
- **Flask-SQLAlchemy** : ORM pour la base de données
- **Flask-Login** : Gestion de l'authentification
- **Flask-WTF** : Formulaires et protection CSRF
- **Flask-CORS** : Support CORS
- **WTForms** : Validation de formulaires
- **Werkzeug** : Utilitaires (hachage de mots de passe)
- **python-dotenv** : Chargement des variables d'environnement
- **Pillow** : Génération d'icônes PWA (optionnel)

---

## Notes importantes

1. **Sécurité** : L'application est configurée pour le développement. Pour la production :
   - Changer `SECRET_KEY`
   - Activer `SESSION_COOKIE_SECURE` et `REMEMBER_COOKIE_SECURE`
   - Utiliser HTTPS

2. **Base de données** : SQLite est utilisé par défaut. Pour la production, considérer PostgreSQL ou MySQL.

3. **Emails** : La configuration email est requise pour certaines fonctionnalités (2FA, reset password, notifications).

4. **Template** : L'application est conçue comme un template de base. Les pages principales (dashboard, graphiques, etc.) sont vides et doivent être implémentées selon les besoins.

---

## Support et contribution

Cette application est un template de base. Elle peut être étendue selon les besoins spécifiques de chaque projet.

