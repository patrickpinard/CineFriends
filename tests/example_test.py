"""
Exemple de tests unitaires pour TemplateApp.

Ce fichier montre comment structurer les tests pour l'application.
Pour utiliser pytest, installer les dépendances de développement :
    pip install -r requirements-dev.txt

Lancer les tests :
    pytest tests/
    pytest tests/ -v  # mode verbeux
    pytest tests/ --cov=app  # avec couverture de code
"""

import pytest
from flask import url_for
from app import create_app, db
from app.models import User


@pytest.fixture
def app():
    """Créer une instance de l'application pour les tests."""
    app = create_app('testing')
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    
    with app.app_context():
        db.create_all()
        yield app
        db.drop_all()
    
    return app


@pytest.fixture
def client(app):
    """Créer un client de test."""
    return app.test_client()


@pytest.fixture
def runner(app):
    """Créer un runner CLI pour les tests."""
    return app.test_cli_runner()


@pytest.fixture
def admin_user(app):
    """Créer un utilisateur administrateur pour les tests."""
    user = User(
        username='admin',
        email='admin@test.com',
        role='admin',
        active=True
    )
    user.set_password('admin123')
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture
def regular_user(app):
    """Créer un utilisateur régulier pour les tests."""
    user = User(
        username='user',
        email='user@test.com',
        role='user',
        active=True
    )
    user.set_password('user123')
    db.session.add(user)
    db.session.commit()
    return user


class TestAuth:
    """Tests pour l'authentification."""
    
    def test_login_page_loads(self, client):
        """Test que la page de connexion se charge."""
        response = client.get('/auth/login')
        assert response.status_code == 200
        assert b'Nom d\'utilisateur' in response.data
    
    def test_login_success(self, client, admin_user):
        """Test de connexion réussie."""
        response = client.post('/auth/login', data={
            'username': 'admin',
            'password': 'admin123'
        }, follow_redirects=True)
        assert response.status_code == 200
    
    def test_login_invalid_credentials(self, client):
        """Test de connexion avec identifiants invalides."""
        response = client.post('/auth/login', data={
            'username': 'invalid',
            'password': 'invalid'
        })
        assert b'Identifiants invalides' in response.data
    
    def test_login_inactive_account(self, client, app):
        """Test de connexion avec compte inactif."""
        user = User(
            username='inactive',
            email='inactive@test.com',
            active=False
        )
        user.set_password('password')
        db.session.add(user)
        db.session.commit()
        
        response = client.post('/auth/login', data={
            'username': 'inactive',
            'password': 'password'
        })
        assert b'en attente d\'activation' in response.data
    
    def test_logout(self, client, admin_user):
        """Test de déconnexion."""
        # Se connecter d'abord
        client.post('/auth/login', data={
            'username': 'admin',
            'password': 'admin123'
        })
        
        # Se déconnecter
        response = client.get('/auth/logout', follow_redirects=True)
        assert response.status_code == 200
        assert b'login' in response.data.lower()


class TestUserManagement:
    """Tests pour la gestion des utilisateurs."""
    
    def test_users_list_requires_auth(self, client):
        """Test que la liste des utilisateurs nécessite une authentification."""
        response = client.get('/admin/utilisateurs')
        assert response.status_code == 302  # Redirection vers login
    
    def test_users_list_requires_admin(self, client, regular_user):
        """Test que la liste des utilisateurs nécessite le rôle admin."""
        # Se connecter comme utilisateur régulier
        client.post('/auth/login', data={
            'username': 'user',
            'password': 'user123'
        })
        
        response = client.get('/admin/utilisateurs')
        assert response.status_code == 302  # Redirection
    
    def test_create_user(self, client, admin_user):
        """Test de création d'utilisateur par un admin."""
        # Se connecter comme admin
        client.post('/auth/login', data={
            'username': 'admin',
            'password': 'admin123'
        })
        
        response = client.post('/admin/utilisateurs/nouveau', data={
            'username': 'newuser',
            'email': 'newuser@test.com',
            'password': 'password123',
            'confirm_password': 'password123',
            'role': 'user',
            'active': True
        }, follow_redirects=True)
        
        assert response.status_code == 200
        # Vérifier que l'utilisateur a été créé
        user = User.query.filter_by(username='newuser').first()
        assert user is not None
        assert user.email == 'newuser@test.com'


class TestProfile:
    """Tests pour le profil utilisateur."""
    
    def test_profile_requires_auth(self, client):
        """Test que le profil nécessite une authentification."""
        response = client.get('/profil')
        assert response.status_code == 302  # Redirection vers login
    
    def test_profile_update(self, client, regular_user):
        """Test de mise à jour du profil."""
        # Se connecter
        client.post('/auth/login', data={
            'username': 'user',
            'password': 'user123'
        })
        
        response = client.post('/profil', data={
            'username': 'user',
            'email': 'updated@test.com',
            'first_name': 'John',
            'last_name': 'Doe'
        }, follow_redirects=True)
        
        assert response.status_code == 200
        # Vérifier que le profil a été mis à jour
        user = User.query.get(regular_user.id)
        assert user.email == 'updated@test.com'
        assert user.first_name == 'John'


class TestModels:
    """Tests pour les modèles."""
    
    def test_user_password_hashing(self, app):
        """Test que les mots de passe sont correctement hashés."""
        user = User(username='test', email='test@test.com')
        user.set_password('password123')
        
        assert user.password_hash != 'password123'
        assert user.check_password('password123')
        assert not user.check_password('wrongpassword')
    
    def test_user_is_active(self, app):
        """Test de la méthode is_active."""
        user = User(username='test', email='test@test.com', active=True)
        assert user.is_active() is True
        
        user.active = False
        assert user.is_active() is False


class TestUtils:
    """Tests pour les utilitaires."""
    
    def test_utcnow(self, app):
        """Test de la fonction utcnow."""
        from app.utils import utcnow
        from datetime import timezone
        
        now = utcnow()
        assert now.tzinfo == timezone.utc
    
    def test_save_avatar(self, app):
        """Test de sauvegarde d'avatar."""
        from app.utils import save_avatar
        from werkzeug.datastructures import FileStorage
        from io import BytesIO
        
        # Créer un fichier de test
        file_content = b'fake image content'
        file = FileStorage(
            stream=BytesIO(file_content),
            filename='test.png',
            content_type='image/png'
        )
        
        with app.app_context():
            filename = save_avatar(file)
            assert filename.startswith('avatar_')
            assert filename.endswith('.png')

