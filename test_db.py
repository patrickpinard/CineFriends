#!/usr/bin/env python3
"""Script de test pour diagnostiquer le problème de connexion à la base de données"""

import sys
import os
from pathlib import Path

# Ajouter le répertoire au path
sys.path.insert(0, str(Path(__file__).parent))

print("=" * 60)
print("TEST DE CONNEXION À LA BASE DE DONNÉES")
print("=" * 60)

# Test 1: Vérifier le chemin
print("\n1. Vérification du chemin...")
base_dir = Path(__file__).resolve().parent
instance_dir = base_dir / "instance"
db_file = instance_dir / "dashboard.db"

print(f"   Répertoire de base: {base_dir}")
print(f"   Répertoire instance: {instance_dir}")
print(f"   Fichier DB: {db_file}")
print(f"   Instance existe: {instance_dir.exists()}")
print(f"   DB existe: {db_file.exists()}")

# Test 2: Créer le répertoire si nécessaire
print("\n2. Création/vérification du répertoire...")
try:
    instance_dir.mkdir(parents=True, exist_ok=True)
    print(f"   ✓ Répertoire créé/vérifié: {instance_dir}")
except Exception as e:
    print(f"   ✗ Erreur: {e}")
    sys.exit(1)

# Test 3: Vérifier les permissions
print("\n3. Vérification des permissions...")
try:
    if os.access(instance_dir, os.W_OK):
        print(f"   ✓ Permissions d'écriture OK sur {instance_dir}")
    else:
        print(f"   ✗ Pas de permission d'écriture sur {instance_dir}")
        print(f"   Propriétaire: {os.stat(instance_dir).st_uid}")
        print(f"   UID actuel: {os.getuid()}")
        sys.exit(1)
except Exception as e:
    print(f"   ✗ Erreur: {e}")
    sys.exit(1)

# Test 4: Connexion SQLite directe
print("\n4. Test de connexion SQLite directe...")
try:
    import sqlite3
    print(f"   Tentative de connexion à: {db_file.resolve()}")
    conn = sqlite3.connect(str(db_file.resolve()), timeout=10.0)
    conn.execute("SELECT 1")
    conn.close()
    print(f"   ✓ Connexion SQLite directe réussie!")
except Exception as e:
    print(f"   ✗ Erreur SQLite: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 5: Test avec SQLAlchemy
print("\n5. Test de connexion SQLAlchemy...")
try:
    from config import Config
    db_uri = Config.SQLALCHEMY_DATABASE_URI
    print(f"   URI configurée: {db_uri}")
    
    # Extraire le chemin et convertir en absolu si nécessaire
    if db_uri.startswith("sqlite:///"):
        # Gérer les 3 et 4 slashes
        if db_uri.startswith("sqlite:////"):
            db_path_from_uri = db_uri.replace("sqlite:////", "")
        else:
            db_path_from_uri = db_uri.replace("sqlite:///", "")
        print(f"   Chemin extrait de l'URI: {db_path_from_uri}")
        db_path_resolved = Path(db_path_from_uri).resolve()
        print(f"   Chemin résolu: {db_path_resolved}")
        
        # Si c'est un chemin relatif, créer une URI avec chemin absolu et 4 slashes
        if not Path(db_path_from_uri).is_absolute():
            print(f"   ⚠ Chemin relatif détecté, conversion en absolu avec 4 slashes...")
            db_path_abs = (base_dir / db_path_from_uri).resolve()
            db_uri = f"sqlite:////{str(db_path_abs).replace(chr(92), '/')}"
            print(f"   Nouvelle URI: {db_uri}")
    
    from sqlalchemy import create_engine, text
    engine = create_engine(db_uri, echo=False)
    with engine.connect() as conn:
        result = conn.execute(text("SELECT 1"))
        print(f"   ✓ Connexion SQLAlchemy réussie!")
except Exception as e:
    print(f"   ✗ Erreur SQLAlchemy: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 6: Test avec l'application Flask
print("\n6. Test avec l'application Flask...")
try:
    from app import create_app
    print("   Création de l'application...")
    app = create_app()
    print("   ✓ Application créée avec succès!")
    
    with app.app_context():
        from app import db
        print("   Test de db.create_all()...")
        db.create_all()
        print("   ✓ db.create_all() réussi!")
        
except Exception as e:
    print(f"   ✗ Erreur Flask: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n" + "=" * 60)
print("✓ TOUS LES TESTS ONT RÉUSSI!")
print("=" * 60)

