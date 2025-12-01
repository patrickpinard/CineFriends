#!/usr/bin/env python3
"""
Script pour vérifier et corriger les colonnes d'adresse dans la table 'user'.
Vérifie si les colonnes existent et les crée si nécessaire.
"""

import sys
from pathlib import Path

# Ajouter le répertoire parent au path pour importer l'application
sys.path.insert(0, str(Path(__file__).parent.parent))

from app import create_app, db
from sqlalchemy import text

def check_and_fix_address_fields():
    """Vérifie et crée les colonnes d'adresse si elles n'existent pas."""
    app = create_app()
    
    with app.app_context():
        try:
            # Vérifier les colonnes existantes
            user_cols = {
                row[1]
                for row in db.session.execute(text("PRAGMA table_info(user)"))
            }
            
            print("Colonnes existantes dans la table 'user':")
            print(f"  {', '.join(sorted(user_cols))}\n")
            
            migrations_needed = []
            
            if "street" not in user_cols:
                migrations_needed.append("street")
            if "postal_code" not in user_cols:
                migrations_needed.append("postal_code")
            if "city_country" not in user_cols:
                migrations_needed.append("city_country")
            
            if not migrations_needed:
                print("✓ Toutes les colonnes d'adresse existent déjà.")
                return
            
            print(f"Colonnes manquantes: {', '.join(migrations_needed)}\n")
            print("Création des colonnes manquantes...")
            
            if "street" not in user_cols:
                db.session.execute(
                    text("ALTER TABLE user ADD COLUMN street VARCHAR(255)")
                )
                db.session.commit()
                print("✓ Colonne 'street' créée")
            
            if "postal_code" not in user_cols:
                db.session.execute(
                    text("ALTER TABLE user ADD COLUMN postal_code VARCHAR(20)")
                )
                db.session.commit()
                print("✓ Colonne 'postal_code' créée")
            
            if "city_country" not in user_cols:
                db.session.execute(
                    text("ALTER TABLE user ADD COLUMN city_country VARCHAR(255)")
                )
                db.session.commit()
                print("✓ Colonne 'city_country' créée")
            
            print("\n✓ Toutes les colonnes d'adresse ont été créées avec succès!")
            
            # Vérifier à nouveau
            user_cols_after = {
                row[1]
                for row in db.session.execute(text("PRAGMA table_info(user)"))
            }
            
            if "street" in user_cols_after and "postal_code" in user_cols_after and "city_country" in user_cols_after:
                print("\n✓ Vérification finale : toutes les colonnes sont présentes.")
            else:
                print("\n⚠ Attention : certaines colonnes semblent toujours manquantes.")
            
        except Exception as e:
            db.session.rollback()
            print(f"✗ Erreur lors de la vérification/création des colonnes: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)

if __name__ == "__main__":
    check_and_fix_address_fields()

