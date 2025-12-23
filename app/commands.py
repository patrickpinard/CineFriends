"""
Commandes CLI Flask pour TemplateApp.

Ce module contient les commandes Flask CLI pour gérer l'application
depuis la ligne de commande.
"""

import click
from flask.cli import with_appcontext

from . import db
from .models import User


@click.command()
@click.option('--start', default=1, type=int, help='Numéro de départ (défaut: 1)')
@click.option('--count', default=10, type=int, help='Nombre d\'utilisateurs à créer (défaut: 10)')
@with_appcontext
def create_test_users(start, count):
    """
    Crée des utilisateurs de test avec le mot de passe "password".
    
    Usage:
        flask create-test-users              # Crée user1 à user10 (défaut)
        flask create-test-users --start 11 --count 5  # Crée user11 à user15
    """
    password = "password"
    created_count = 0
    skipped_count = 0
    
    end = start + count
    for i in range(start, end):
        username = f"user{i}"
        email = f"user{i}@example.com"
        
        # Vérifier si l'utilisateur existe déjà
        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            click.echo(f"⚠️  Utilisateur '{username}' existe déjà, ignoré.")
            skipped_count += 1
            continue
        
        # Créer l'utilisateur
        user = User(
            username=username,
            email=email,
            role="user",
            active=True,
            first_name=f"Prénom{i}",
            last_name=f"Nom{i}",
        )
        user.set_password(password)
        
        db.session.add(user)
        created_count += 1
        click.echo(f"✅ Utilisateur '{username}' créé (email: {email})")
    
    if created_count > 0:
        db.session.commit()
        click.echo(f"\n✅ {created_count} utilisateur(s) créé(s) avec succès.")
        click.echo(f"   Mot de passe par défaut pour tous : '{password}'")
    
    if skipped_count > 0:
        click.echo(f"⚠️  {skipped_count} utilisateur(s) déjà existant(s), ignoré(s).")
    
    if created_count == 0 and skipped_count == 0:
        click.echo("ℹ️  Aucun utilisateur à créer.")


@click.command()
@with_appcontext
def list_users():
    """
    Liste tous les utilisateurs de l'application.
    
    Usage:
        flask list-users
    """
    users = User.query.order_by(User.username).all()
    
    if not users:
        click.echo("Aucun utilisateur trouvé.")
        return
    
    click.echo(f"\n{'Username':<20} {'Email':<30} {'Rôle':<10} {'Actif':<8}")
    click.echo("-" * 70)
    
    for user in users:
        active = "Oui" if user.active else "Non"
        email = user.email or "(aucun)"
        click.echo(f"{user.username:<20} {email:<30} {user.role:<10} {active:<8}")
    
    click.echo(f"\nTotal: {len(users)} utilisateur(s)")


@click.command()
@click.argument('username')
@click.option('--password', prompt=True, hide_input=True, confirmation_prompt=True,
              help='Nouveau mot de passe')
@with_appcontext
def reset_password(username, password):
    """
    Réinitialise le mot de passe d'un utilisateur.
    
    Usage:
        flask reset-password <username>
    """
    user = User.query.filter_by(username=username).first()
    
    if not user:
        click.echo(f"❌ Utilisateur '{username}' non trouvé.", err=True)
        return
    
    user.set_password(password)
    db.session.commit()
    
    click.echo(f"✅ Mot de passe réinitialisé pour l'utilisateur '{username}'.")


def register_commands(app):
    """
    Enregistre les commandes CLI dans l'application Flask.
    
    Args:
        app: Instance de l'application Flask
    """
    app.cli.add_command(create_test_users)
    app.cli.add_command(list_users)
    app.cli.add_command(reset_password)

