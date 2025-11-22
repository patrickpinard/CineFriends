#!/usr/bin/env python3
"""
Script de diagnostic pour tester la sonde DS18B20.
"""

import sys
from pathlib import Path
from datetime import datetime

# Ajouter le répertoire parent au path pour importer l'application
sys.path.insert(0, str(Path(__file__).parent.parent))

from app import create_app, db
from app.utils import detect_ds18b20
from app.models import Setting

app = create_app()

print("=" * 60)
print("Diagnostic DS18B20")
print("=" * 60)

with app.app_context():
    # Afficher la configuration
    print("\n1. Configuration:")
    setting = Setting.query.filter_by(key="Sensor_DS18B20_Interface").first()
    if setting:
        print(f"   Interface 1-Wire configurée: {setting.value}")
    else:
        print("   Interface 1-Wire: non configurée (utilisera 'w1' par défaut)")
    
    setting_name = Setting.query.filter_by(key="Sensor_Name_DS18B20").first()
    if setting_name:
        print(f"   Nom de la sonde: {setting_name.value}")
    
    # Vérifier le module 1-Wire
    print("\n2. Vérification du module 1-Wire:")
    import os
    if os.path.exists("/sys/bus/w1/devices"):
        print("   ✓ /sys/bus/w1/devices existe")
        try:
            devices = os.listdir("/sys/bus/w1/devices")
            w1_devices = [d for d in devices if d.startswith("28-")]
            if w1_devices:
                print(f"   ✓ {len(w1_devices)} capteur(s) DS18B20 détecté(s):")
                for device in w1_devices:
                    print(f"     - {device}")
            else:
                print("   ✗ Aucun capteur DS18B20 détecté dans /sys/bus/w1/devices")
                print("   → Vérifiez que:")
                print("     - Le module w1-gpio est chargé (modprobe w1-gpio)")
                print("     - Le module w1-therm est chargé (modprobe w1-therm)")
                print("     - Le capteur est correctement câblé")
        except PermissionError:
            print("   ✗ Permission refusée pour /sys/bus/w1/devices")
        except Exception as exc:
            print(f"   ✗ Erreur: {exc}")
    else:
        print("   ✗ /sys/bus/w1/devices n'existe pas")
        print("   → Le module 1-Wire n'est pas activé")
        print("   → Activez-le avec: sudo modprobe w1-gpio && sudo modprobe w1-therm")
    
    # Tester la détection
    print("\n3. Test de détection:")
    try:
        status = detect_ds18b20()
        print(f"   Statut: {status.get('status')}")
        print(f"   Message: {status.get('message')}")
        details = status.get('details', {})
        if details:
            print(f"   Détails: {details}")
            sensors = details.get('sensors', [])
            temperatures = details.get('temperatures', [])
            if sensors and temperatures:
                print("   ✓ Mesures disponibles:")
                for sensor_id, temp in zip(sensors, temperatures):
                    if temp is not None:
                        print(f"     - {sensor_id}: {temp}°C")
                    else:
                        print(f"     - {sensor_id}: lecture en cours...")
            else:
                print("   ✗ Aucune mesure disponible")
    except Exception as exc:
        print(f"   ✗ Erreur: {exc}")
        import traceback
        traceback.print_exc()
    
    # Tester directement le driver w1thermsensor
    print("\n4. Test direct du driver w1thermsensor:")
    try:
        from w1thermsensor import W1ThermSensor, NoSensorFoundError, SensorNotReadyError
        
        print("   Recherche des capteurs...")
        try:
            sensors = W1ThermSensor.get_available_sensors()
            if not sensors:
                print("   ✗ Aucun capteur trouvé")
            else:
                print(f"   ✓ {len(sensors)} capteur(s) trouvé(s)")
                for i, sensor in enumerate(sensors, 1):
                    print(f"\n   Capteur {i}:")
                    print(f"     ID: {sensor.id}")
                    print(f"     Type: {sensor.type_name}")
                    try:
                        temp = sensor.get_temperature()
                        print(f"     ✓ Température: {temp}°C")
                    except SensorNotReadyError:
                        print(f"     ⚠ Lecture en cours (attendre quelques secondes)")
                    except Exception as exc:
                        print(f"     ✗ Erreur de lecture: {exc}")
        except NoSensorFoundError:
            print("   ✗ Aucun capteur DS18B20 trouvé")
            print("   → Vérifiez:")
            print("     - Le câblage (VCC, GND, DATA)")
            print("     - La résistance pull-up de 4.7kΩ")
            print("     - Que les modules w1-gpio et w1-therm sont chargés")
        except Exception as exc:
            print(f"   ✗ Erreur: {exc}")
            import traceback
            traceback.print_exc()
    except ImportError:
        print("   ✗ Bibliothèque w1thermsensor non installée")
        print("   → Installez-la avec: pip install w1thermsensor")
    except Exception as exc:
        print(f"   ✗ Erreur: {exc}")
        import traceback
        traceback.print_exc()
    
    # Vérifier les modules kernel
    print("\n5. Vérification des modules kernel:")
    try:
        import subprocess
        result = subprocess.run(['lsmod'], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            modules = result.stdout
            if 'w1_gpio' in modules:
                print("   ✓ Module w1_gpio chargé")
            else:
                print("   ✗ Module w1_gpio non chargé")
                print("   → Chargez-le avec: sudo modprobe w1-gpio")
            
            if 'w1_therm' in modules:
                print("   ✓ Module w1_therm chargé")
            else:
                print("   ✗ Module w1_therm non chargé")
                print("   → Chargez-le avec: sudo modprobe w1-therm")
        else:
            print("   ⚠ Impossible de vérifier les modules (besoin de sudo)")
    except FileNotFoundError:
        print("   - lsmod non disponible")
    except subprocess.TimeoutExpired:
        print("   ✗ Timeout lors de la vérification")
    except Exception as exc:
        print(f"   ✗ Erreur: {exc}")
    
    # Test avec retry
    print("\n6. Test avec retry amélioré:")
    try:
        from w1thermsensor import W1ThermSensor, SensorNotReadyError
        import time
        
        sensors = W1ThermSensor.get_available_sensors()
        if not sensors:
            print("   ✗ Aucun capteur disponible pour le test")
        else:
            for sensor in sensors:
                print(f"   Test du capteur {sensor.id}...")
                for attempt in range(3):
                    try:
                        print(f"   Tentative {attempt + 1}/3...")
                        temp = sensor.get_temperature()
                        print(f"   ✓ SUCCÈS! Température: {temp}°C")
                        break
                    except SensorNotReadyError:
                        print(f"   ⚠ Capteur pas encore prêt (attente 2 secondes...)")
                        if attempt < 2:
                            time.sleep(2)
                        else:
                            print("   ✗ Capteur toujours pas prêt après 3 tentatives")
                    except Exception as exc:
                        print(f"   ✗ Erreur: {exc}")
                        break
    except Exception as exc:
        print(f"   ✗ Erreur lors du test: {exc}")
        import traceback
        traceback.print_exc()

print("\n" + "=" * 60)
print("Diagnostic terminé")
print("=" * 60)

