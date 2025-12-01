#!/usr/bin/env python3
"""
Script de migration pour ajouter les colonnes 'city', 'country' et 'phone' à la table 'user'.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app import create_app, db
from sqlalchemy import text

def add_city_country_phone_fields():
    """Ajoute les colonnes 'city', 'country' et 'phone' à la table 'user' si elles n'existent pas."""
    app = create_app()
    
    with app.app_context():
        try:
            user_cols = {
                row[1]
                for row in db.session.execute(text("PRAGMA table_info(user)"))
            }
            
            migrations_applied = []
            
            if "city" not in user_cols:
                db.session.execute(
                    text("ALTER TABLE user ADD COLUMN city VARCHAR(255)")
                )
                db.session.commit()
                migrations_applied.append("city")
                print("✓ Colonne 'city' créée")
            
            if "country" not in user_cols:
                db.session.execute(
                    text("ALTER TABLE user ADD COLUMN country VARCHAR(255)")
                )
                db.session.commit()
                migrations_applied.append("country")
                print("✓ Colonne 'country' créée")
            
            if "phone" not in user_cols:
                db.session.execute(
                    text("ALTER TABLE user ADD COLUMN phone VARCHAR(50)")
                )
                db.session.commit()
                migrations_applied.append("phone")
                print("✓ Colonne 'phone' créée")
            
            if not migrations_applied:
                print("✓ Toutes les colonnes existent déjà.")
            else:
                print(f"\n✓ Migrations appliquées: {', '.join(migrations_applied)}")
            
        except Exception as e:
            db.session.rollback()
            print(f"✗ Erreur: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)

if __name__ == "__main__":
    add_city_country_phone_fields()

