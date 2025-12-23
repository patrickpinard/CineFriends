# Changelog

Tous les changements notables de ce projet seront documentés dans ce fichier.

## [2.0.0] - 2025-01-XX

### ✨ Ajouté

- **Configuration multi-environnements** : Support pour development, testing et production
- **Flask-Migrate** : Système de migrations de base de données
- **Rate Limiting** : Protection contre les attaques par force brute
  - Login : 5 tentatives par minute
  - Register : 3 tentatives par heure
  - Reset Password : 3 tentatives par heure
- **Headers de sécurité** : Flask-Talisman pour HSTS, CSP, etc.
- **Health check endpoint** : `/health` pour le monitoring
- **Pagination** : Pagination pour la liste des utilisateurs
- **Cache** : Support pour Flask-Caching (simple, Redis, etc.)
- **Docker** : Dockerfile et docker-compose.yml complets
- **Tests** : Framework de tests avec pytest et exemples
- **Documentation** : README.md complet et guides d'implémentation

### 🔧 Modifié

- **Configuration** : Refactorisation avec classes par environnement
- **Requirements** : Ajout des nouvelles dépendances
- **Admin** : Pagination pour la liste des utilisateurs
- **Sécurité** : Headers de sécurité automatiques

### 📚 Documentation

- README.md complet avec instructions d'installation
- Guide d'implémentation des améliorations
- Analyse détaillée avec recommandations
- Exemples de tests unitaires

## [1.0.0] - Version initiale

### Fonctionnalités de base

- Authentification complète (login, register, 2FA, reset password)
- Gestion des utilisateurs (CRUD)
- Système de notifications
- Progressive Web App (PWA)
- Logging structuré
- Templates avec Tailwind CSS

---

## Format

Le format est basé sur [Keep a Changelog](https://keepachangelog.com/fr/1.0.0/),
et ce projet adhère à [Semantic Versioning](https://semver.org/lang/fr/).

### Types de changements

- **Ajouté** : Nouvelles fonctionnalités
- **Modifié** : Changements dans les fonctionnalités existantes
- **Déprécié** : Fonctionnalités qui seront supprimées
- **Supprimé** : Fonctionnalités supprimées
- **Corrigé** : Corrections de bugs
- **Sécurité** : Corrections de vulnérabilités

