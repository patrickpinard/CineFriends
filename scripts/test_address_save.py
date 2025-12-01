#!/usr/bin/env python3
"""
Script pour tester la sauvegarde des champs d'adresse.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app import create_app, db
from app.models import User
from sqlalchemy import text

def test_address_save():
    """Teste la sauvegarde des champs d'adresse."""
    app = create_app()
    
    with app.app_context():
        try:
            # Récupérer l'utilisateur admin
            user = User.query.filter_by(username='admin').first()
            
            if not user:
                print("✗ Utilisateur 'admin' non trouvé")
                return
            
            print(f"Utilisateur trouvé: {user.username}")
            print(f"Email: {user.email}")
            print(f"Street (avant): {getattr(user, 'street', 'N/A')}")
            print(f"Postal code (avant): {getattr(user, 'postal_code', 'N/A')}")
            print(f"City/Country (avant): {getattr(user, 'city_country', 'N/A')}")
            
            # Modifier les valeurs
            user.street = "123 Rue de Test"
            user.postal_code = "1234"
            user.city_country = "Test City, Test Country"
            
            db.session.add(user)
            db.session.commit()
            
            print("\n✓ Valeurs modifiées et commit effectué")
            
            # Vérifier directement dans la DB
            result = db.session.execute(
                text("SELECT street, postal_code, city_country FROM user WHERE username = 'admin'")
            ).fetchone()
            
            if result:
                print(f"\nValeurs dans la DB:")
                print(f"  Street: {result[0]}")
                print(f"  Postal code: {result[1]}")
                print(f"  City/Country: {result[2]}")
            
            # Recharger l'utilisateur depuis la DB
            db.session.expire(user)
            user = User.query.filter_by(username='admin').first()
            
            print(f"\nValeurs après rechargement:")
            print(f"  Street: {getattr(user, 'street', 'N/A')}")
            print(f"  Postal code: {getattr(user, 'postal_code', 'N/A')}")
            print(f"  City/Country: {getattr(user, 'city_country', 'N/A')}")
            
        except Exception as e:
            db.session.rollback()
            print(f"✗ Erreur: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)

if __name__ == "__main__":
    test_address_save()

