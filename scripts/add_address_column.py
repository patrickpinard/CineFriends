#!/usr/bin/env python3
"""
Script de migration pour ajouter la colonne 'address' à la table 'user'.
À exécuter manuellement si la migration automatique n'a pas fonctionné.
"""

import sys
from pathlib import Path

# Ajouter le répertoire parent au path pour importer l'application
sys.path.insert(0, str(Path(__file__).parent.parent))

from app import create_app, db
from sqlalchemy import text

def add_address_column():
    """Ajoute la colonne 'address' à la table 'user' si elle n'existe pas."""
    app = create_app()
    
    with app.app_context():
        try:
            # Vérifier si la colonne existe déjà
            user_cols = {
                row[1]
                for row in db.session.execute(text("PRAGMA table_info(user)"))
            }
            
            if "address" in user_cols:
                print("✓ La colonne 'address' existe déjà dans la table 'user'.")
                return
            
            # Ajouter la colonne
            print("Ajout de la colonne 'address' à la table 'user'...")
            db.session.execute(
                text("ALTER TABLE user ADD COLUMN address VARCHAR(255)")
            )
            db.session.commit()
            print("✓ Colonne 'address' ajoutée avec succès!")
            
        except Exception as e:
            db.session.rollback()
            print(f"✗ Erreur lors de l'ajout de la colonne: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)

if __name__ == "__main__":
    add_address_column()

