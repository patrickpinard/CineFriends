#!/usr/bin/env python3
"""
Script de diagnostic pour tester les relais.
"""

import sys
from pathlib import Path
from datetime import datetime

# Ajouter le répertoire parent au path pour importer l'application
sys.path.insert(0, str(Path(__file__).parent.parent))

from app import create_app, db
from app.utils import detect_gpio_relays
from app.models import Setting
from app.hardware.gpio_controller import (
    get_configured_relay_pins,
    get_relay_states,
    set_relay_state,
    get_relay_labels,
    hardware_available,
    is_active_low,
)

app = create_app()

print("=" * 60)
print("Diagnostic Relais")
print("=" * 60)

with app.app_context():
    # Afficher la configuration
    print("\n1. Configuration:")
    relay_pins = get_configured_relay_pins()
    relay_labels = get_relay_labels()
    
    if not relay_pins:
        print("   ✗ Aucun relais configuré")
    else:
        print(f"   ✓ {len(relay_pins)} relais configuré(s):")
        for channel, pin in sorted(relay_pins.items()):
            label = relay_labels.get(channel, f"Relais {channel}")
            print(f"     - Canal {channel}: GPIO {pin} ({label})")
    
    # Vérifier les paramètres
    print("\n2. Paramètres des relais:")
    for channel in [1, 2, 3]:
        pin_key = f"Relay_Ch{channel}"
        name_key = f"Relay_Name_Ch{channel}"
        
        pin_setting = Setting.query.filter_by(key=pin_key).first()
        name_setting = Setting.query.filter_by(key=name_key).first()
        
        pin_value = pin_setting.value if pin_setting else "non configuré"
        name_value = name_setting.value if name_setting else f"Relais {channel}"
        
        print(f"   Canal {channel}:")
        print(f"     - GPIO: {pin_value}")
        print(f"     - Nom: {name_value}")
    
    # Vérifier la disponibilité du hardware
    print("\n3. Vérification du hardware:")
    available = hardware_available()
    if available:
        print("   ✓ Hardware disponible (Raspberry Pi détecté)")
    else:
        print("   ✗ Hardware non disponible (pas sur Raspberry Pi)")
        print("   → Les tests suivants seront limités")
    
    active_low = is_active_low()
    print(f"   Mode: {'Active Low' if active_low else 'Active High'}")
    
    # Tester la détection
    print("\n4. Test de détection:")
    if relay_pins:
        try:
            status = detect_gpio_relays(relay_pins.values())
            print(f"   Statut: {status.get('status')}")
            print(f"   Message: {status.get('message')}")
            details = status.get('details', {})
            if details:
                print(f"   Détails: {details}")
        except Exception as exc:
            print(f"   ✗ Erreur: {exc}")
            import traceback
            traceback.print_exc()
    else:
        print("   - Aucun relais configuré, test de détection ignoré")
    
    # Vérifier RPi.GPIO
    print("\n5. Vérification de RPi.GPIO:")
    try:
        import RPi.GPIO as GPIO
        print("   ✓ RPi.GPIO disponible")
        print(f"   Version: {GPIO.VERSION if hasattr(GPIO, 'VERSION') else 'N/A'}")
    except ImportError:
        print("   ✗ RPi.GPIO non disponible")
        print("   → Installez-le avec: pip install RPi.GPIO")
        print("   → Ou: sudo apt-get install python3-rpi.gpio")
    except Exception as exc:
        print(f"   ✗ Erreur: {exc}")
    
    # Tester la lecture des états
    print("\n6. Test de lecture des états:")
    if relay_pins and available:
        try:
            states = get_relay_states()
            if states:
                print("   ✓ États des relais:")
                for channel, pin in sorted(relay_pins.items()):
                    state = states.get(channel, "unknown")
                    label = relay_labels.get(channel, f"Relais {channel}")
                    print(f"     - Canal {channel} ({label}): {state.upper()}")
            else:
                print("   ✗ Impossible de lire les états")
        except Exception as exc:
            print(f"   ✗ Erreur lors de la lecture: {exc}")
            import traceback
            traceback.print_exc()
    else:
        print("   - Test ignoré (hardware non disponible ou aucun relais configuré)")
    
    # Test interactif (optionnel)
    print("\n7. Test interactif (optionnel):")
    if relay_pins and available:
        print("   Pour tester chaque relais, vous pouvez utiliser:")
        print("   - L'interface web du dashboard")
        print("   - Ou exécuter ce script avec l'option --test")
        print("\n   Exemple de commande pour tester:")
        for channel, pin in sorted(relay_pins.items()):
            label = relay_labels.get(channel, f"Relais {channel}")
            print(f"     Canal {channel} ({label}):")
            print(f"       ON:  set_relay_state({channel}, 'on')")
            print(f"       OFF: set_relay_state({channel}, 'off')")
        
        # Si l'option --test est passée, faire un test automatique
        if '--test' in sys.argv:
            print("\n   Exécution d'un test automatique...")
            import time
            for channel, pin in sorted(relay_pins.items()):
                label = relay_labels.get(channel, f"Relais {channel}")
                print(f"\n   Test du canal {channel} ({label})...")
                try:
                    # Lire l'état initial
                    initial_state = get_relay_states().get(channel, "unknown")
                    print(f"     État initial: {initial_state}")
                    
                    # Allumer
                    print(f"     → Allumage...")
                    result = set_relay_state(channel, "on")
                    if result.get("status") == "ok":
                        print(f"     ✓ Allumé avec succès")
                        time.sleep(1)
                    else:
                        print(f"     ✗ Erreur: {result.get('message')}")
                    
                    # Éteindre
                    print(f"     → Extinction...")
                    result = set_relay_state(channel, "off")
                    if result.get("status") == "ok":
                        print(f"     ✓ Éteint avec succès")
                        time.sleep(1)
                    else:
                        print(f"     ✗ Erreur: {result.get('message')}")
                    
                    # Restaurer l'état initial si nécessaire
                    if initial_state.lower() in ["on", "off"]:
                        print(f"     → Restauration de l'état initial ({initial_state})...")
                        set_relay_state(channel, initial_state.lower())
                    
                except Exception as exc:
                    print(f"     ✗ Erreur lors du test: {exc}")
                    import traceback
                    traceback.print_exc()
    else:
        print("   - Test interactif non disponible")
    
    # Vérifier les permissions GPIO
    print("\n8. Vérification des permissions GPIO:")
    import os
    if os.path.exists("/dev/gpiomem"):
        try:
            with open("/dev/gpiomem", "rb") as f:
                print("   ✓ /dev/gpiomem accessible")
        except PermissionError:
            print("   ✗ Permission refusée pour /dev/gpiomem")
            print("   → Ajoutez l'utilisateur au groupe gpio:")
            print("     sudo usermod -a -G gpio $USER")
            print("     (puis reconnectez-vous)")
    else:
        print("   - /dev/gpiomem n'existe pas")
    
    if os.path.exists("/sys/class/gpio"):
        try:
            gpios = os.listdir("/sys/class/gpio")
            print(f"   ✓ /sys/class/gpio accessible ({len(gpios)} entrées)")
        except PermissionError:
            print("   ✗ Permission refusée pour /sys/class/gpio")
        except Exception as exc:
            print(f"   ⚠ Erreur: {exc}")
    else:
        print("   - /sys/class/gpio n'existe pas")

print("\n" + "=" * 60)
print("Diagnostic terminé")
print("=" * 60)
print("\nPour tester les relais automatiquement, exécutez:")
print("  python3 scripts/test_relays.py --test")

