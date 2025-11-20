#!/usr/bin/env python3
import sys
import traceback

print("=== Test de démarrage de l'application ===")
print(f"Python: {sys.version}")
print(f"Chemin: {sys.path[0]}")

try:
    print("\n1. Import de l'application...")
    from app import create_app
    print("   ✓ Import réussi")
    
    print("\n2. Création de l'application...")
    app = create_app()
    print("   ✓ Application créée")
    
    print("\n3. Démarrage du serveur...")
    print("   → Serveur disponible sur http://localhost:8080")
    print("   → Appuyez sur Ctrl+C pour arrêter")
    
    app.run(host="0.0.0.0", port=8080, debug=True)
    
except KeyboardInterrupt:
    print("\n\nArrêt demandé par l'utilisateur")
    sys.exit(0)
except Exception as e:
    print(f"\n❌ ERREUR: {e}")
    traceback.print_exc()
    sys.exit(1)

