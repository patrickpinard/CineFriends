#!/usr/bin/env python3
"""
Script pour purger les mesures de capteurs jusqu'à aujourd'hui.
"""

import sys
from pathlib import Path
from datetime import datetime

# Ajouter le répertoire parent au path pour importer l'application
sys.path.insert(0, str(Path(__file__).parent.parent))

from app import create_app, db
from app.models import SensorReading, JournalEntry

app = create_app()

with app.app_context():
    # Supprimer toutes les mesures jusqu'à aujourd'hui (avant minuit aujourd'hui)
    today = datetime.utcnow().date()
    threshold = datetime.combine(today, datetime.min.time())

    query = SensorReading.query.filter(SensorReading.created_at < threshold)
    count = query.count()
    
    if count == 0:
        print("Aucune mesure à supprimer.")
        sys.exit(0)

    print(f"Suppression de {count} mesure(s) jusqu'à aujourd'hui...")
    
    query.delete(synchronize_session=False)
    
    db.session.add(
        JournalEntry(
            level="warning",
            message="Purge des mesures capteurs (script)",
            details={
                "deleted_before": threshold.isoformat(),
                "deleted_count": count,
                "performed_by": "script",
            },
        )
    )
    
    db.session.commit()
    print(f"✓ {count} mesure(s) supprimée(s) avec succès.")

