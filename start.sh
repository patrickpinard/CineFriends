#!/bin/bash
cd "$(dirname "$0")"
echo "=== Démarrage du Dashboard ==="
echo "Répertoire: $(pwd)"
echo "Python: $(python3 --version)"
echo ""
echo "Vérification des dépendances..."
python3 -c "import flask; print('✓ Flask installé')" 2>&1 || echo "✗ Flask manquant - installez avec: pip3 install flask"
python3 -c "import flask_login; print('✓ Flask-Login installé')" 2>&1 || echo "✗ Flask-Login manquant"
python3 -c "import flask_sqlalchemy; print('✓ Flask-SQLAlchemy installé')" 2>&1 || echo "✗ Flask-SQLAlchemy manquant"
echo ""
echo "Démarrage de l'application..."
echo "→ L'application sera disponible sur http://localhost:8080"
echo "→ Appuyez sur Ctrl+C pour arrêter"
echo ""
python3 run.py

