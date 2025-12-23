"""
Configuration pytest pour TemplateApp.

Ce fichier contient les fixtures partagées pour tous les tests.
"""

import pytest
from app import create_app, db
from app.models import User


@pytest.fixture(scope='session')
def app():
    """Créer une instance de l'application pour les tests."""
    app = create_app('testing')
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    
    with app.app_context():
        db.create_all()
        yield app
        db.drop_all()


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
    with app.app_context():
        user = User(
            username='admin',
            email='admin@test.com',
            role='admin',
            active=True
        )
        user.set_password('admin123')
        db.session.add(user)
        db.session.commit()
        yield user
        db.session.delete(user)
        db.session.commit()


@pytest.fixture
def regular_user(app):
    """Créer un utilisateur régulier pour les tests."""
    with app.app_context():
        user = User(
            username='user',
            email='user@test.com',
            role='user',
            active=True
        )
        user.set_password('user123')
        db.session.add(user)
        db.session.commit()
        yield user
        db.session.delete(user)
        db.session.commit()

