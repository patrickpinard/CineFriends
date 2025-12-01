#!/usr/bin/env python3
"""
Script de migration pour ajouter les colonnes 'street', 'postal_code' et 'city_country' à la table 'user'.
À exécuter manuellement si la migration automatique n'a pas fonctionné.
"""

import sys
from pathlib import Path

# Ajouter le répertoire parent au path pour importer l'application
sys.path.insert(0, str(Path(__file__).parent.parent))

from app import create_app, db
from sqlalchemy import text

def add_address_fields():
    """Ajoute les colonnes 'street', 'postal_code' et 'city_country' à la table 'user' si elles n'existent pas."""
    app = create_app()
    
    with app.app_context():
        try:
            # Vérifier si les colonnes existent déjà
            user_cols = {
                row[1]
                for row in db.session.execute(text("PRAGMA table_info(user)"))
            }
            
            migrations_applied = []
            
            if "street" not in user_cols:
                print("Ajout de la colonne 'street' à la table 'user'...")
                db.session.execute(
                    text("ALTER TABLE user ADD COLUMN street VARCHAR(255)")
                )
                db.session.commit()
                migrations_applied.append("street")
                print("✓ Colonne 'street' ajoutée avec succès!")
            else:
                print("✓ La colonne 'street' existe déjà.")
            
            if "postal_code" not in user_cols:
                print("Ajout de la colonne 'postal_code' à la table 'user'...")
                db.session.execute(
                    text("ALTER TABLE user ADD COLUMN postal_code VARCHAR(20)")
                )
                db.session.commit()
                migrations_applied.append("postal_code")
                print("✓ Colonne 'postal_code' ajoutée avec succès!")
            else:
                print("✓ La colonne 'postal_code' existe déjà.")
            
            if "city_country" not in user_cols:
                print("Ajout de la colonne 'city_country' à la table 'user'...")
                db.session.execute(
                    text("ALTER TABLE user ADD COLUMN city_country VARCHAR(255)")
                )
                db.session.commit()
                migrations_applied.append("city_country")
                print("✓ Colonne 'city_country' ajoutée avec succès!")
            else:
                print("✓ La colonne 'city_country' existe déjà.")
            
            if not migrations_applied:
                print("\n✓ Toutes les colonnes existent déjà. Aucune migration nécessaire.")
            else:
                print(f"\n✓ Migrations appliquées: {', '.join(migrations_applied)}")
            
        except Exception as e:
            db.session.rollback()
            print(f"✗ Erreur lors de l'ajout des colonnes: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)

if __name__ == "__main__":
    add_address_fields()

