# Guide de Migration vers la Version 2.0

Ce guide explique comment migrer votre application vers la version 2.0 avec les nouvelles améliorations.

## 🎯 Changements Principaux

### 1. Configuration Multi-Environnements

**Avant** : Une seule classe `Config`

**Maintenant** : Classes séparées pour chaque environnement
- `DevelopmentConfig` : Développement
- `TestingConfig` : Tests
- `ProductionConfig` : Production

**Action requise** :
1. Vérifier que votre fichier `.env` contient `FLASK_ENV=development` (ou `production`)
2. La configuration s'adapte automatiquement selon cette variable

### 2. Flask-Migrate

**Avant** : Migrations manuelles avec ALTER TABLE dans `__init__.py`

**Maintenant** : Système de migrations Flask-Migrate

**Action requise** :
```bash
# Initialiser Flask-Migrate (première fois seulement)
flask db init

# Créer une migration initiale basée sur vos modèles actuels
flask db migrate -m "Initial migration"

# Appliquer la migration
flask db upgrade
```

**Note** : Les migrations automatiques dans `__init__.py` sont toujours présentes pour la compatibilité, mais il est recommandé d'utiliser Flask-Migrate pour les futures modifications.

### 3. Rate Limiting

**Nouveau** : Protection automatique contre les attaques par force brute

**Limites par défaut** :
- Login : 5 tentatives par minute
- Register : 3 tentatives par heure
- Reset Password : 3 tentatives par heure

**Personnalisation** : Modifier dans `app/__init__.py` :
```python
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"]
)
```

### 4. Headers de Sécurité

**Nouveau** : Headers de sécurité automatiques via Flask-Talisman

Aucune action requise, activé automatiquement.

**En production** : S'assurer que `SESSION_COOKIE_SECURE=True` dans `.env`

### 5. Health Check

**Nouveau** : Endpoint `/health` pour le monitoring

**Utilisation** :
```bash
curl http://localhost:8080/health
```

Réponse :
```json
{
  "status": "ok",
  "database": "ok",
  "timestamp": "2025-01-XX..."
}
```

### 6. Pagination

**Avant** : Tous les utilisateurs chargés en mémoire

**Maintenant** : Pagination automatique (20 par page par défaut)

**Utilisation dans les templates** :
```jinja2
{% for user in pagination.items %}
  {# ... #}
{% endfor %}

{# Navigation de pagination #}
{% if pagination.has_prev %}
  <a href="?page={{ pagination.prev_num }}">Précédent</a>
{% endif %}

Page {{ pagination.page }} sur {{ pagination.pages }}

{% if pagination.has_next %}
  <a href="?page={{ pagination.next_num }}">Suivant</a>
{% endif %}
```

## 📦 Nouvelles Dépendances

Installer les nouvelles dépendances :

```bash
pip install -r requirements.txt
```

Nouvelles dépendances ajoutées :
- `flask-migrate==4.0.5` : Migrations
- `flask-limiter==3.5.0` : Rate limiting
- `flask-talisman==1.1.0` : Headers de sécurité
- `flask-caching==2.1.0` : Cache (optionnel)

## 🔄 Étapes de Migration

### Étape 1 : Sauvegarder votre base de données

```bash
# Pour SQLite
cp instance/database.db instance/database.db.backup

# Pour PostgreSQL
pg_dump templateapp > backup.sql
```

### Étape 2 : Mettre à jour le code

```bash
git pull  # ou récupérer les nouveaux fichiers
```

### Étape 3 : Installer les dépendances

```bash
pip install -r requirements.txt
```

### Étape 4 : Initialiser Flask-Migrate

```bash
flask db init
```

### Étape 5 : Créer la migration initiale

```bash
flask db migrate -m "Migration vers v2.0"
```

**Important** : Vérifier le fichier de migration généré dans `migrations/versions/` avant de l'appliquer.

### Étape 6 : Appliquer la migration

```bash
flask db upgrade
```

### Étape 7 : Tester

```bash
python run.py
```

Vérifier que :
- L'application démarre sans erreur
- La connexion fonctionne
- Les routes principales sont accessibles

## ⚠️ Points d'Attention

### 1. Variables d'environnement

Vérifier que votre `.env` contient :
```env
FLASK_ENV=development  # ou production
FLASK_SECRET_KEY=...   # Doit être défini
```

### 2. Base de données en production

En production, `DATABASE_URL` doit être défini :
```env
DATABASE_URL=postgresql://user:password@host:5432/dbname
```

### 3. Rate Limiting

Si vous avez des tests automatisés, vous devrez peut-être ajuster les limites ou les désactiver en mode test.

### 4. Headers de sécurité

En développement avec HTTP, certains headers peuvent causer des warnings dans la console. C'est normal.

## 🐛 Problèmes Courants

### Erreur : "No such command 'db'"

**Solution** : Vérifier que Flask-Migrate est installé :
```bash
pip install flask-migrate
```

### Erreur : "Target database is not up to date"

**Solution** :
```bash
flask db stamp head
flask db migrate -m "New migration"
flask db upgrade
```

### Rate limiting trop restrictif

**Solution** : Modifier les limites dans `app/__init__.py` ou désactiver en développement :
```python
if app.config.get('TESTING'):
    limiter.enabled = False
```

## 📚 Ressources

- [Flask-Migrate Documentation](https://flask-migrate.readthedocs.io/)
- [Flask-Limiter Documentation](https://flask-limiter.readthedocs.io/)
- [Flask-Talisman Documentation](https://github.com/GoogleCloudPlatform/flask-talisman)

## ✅ Checklist de Migration

- [ ] Sauvegarder la base de données
- [ ] Mettre à jour le code
- [ ] Installer les nouvelles dépendances
- [ ] Initialiser Flask-Migrate
- [ ] Créer et vérifier la migration
- [ ] Appliquer la migration
- [ ] Tester l'application
- [ ] Vérifier les logs pour les erreurs
- [ ] Mettre à jour la documentation du projet

## 🆘 Support

En cas de problème :
1. Vérifier les logs dans `logs/app.log`
2. Consulter `ANALYSE_ET_AMELIORATIONS.md` pour plus de détails
3. Vérifier que toutes les dépendances sont installées
4. Vérifier la configuration dans `.env`

---

**Note** : Cette migration est rétrocompatible. Les migrations automatiques dans `__init__.py` continuent de fonctionner pour assurer la compatibilité avec les bases de données existantes.

