#!/usr/bin/env python3
"""
Script de diagnostic pour tester la sonde AM2315.
"""

import sys
from pathlib import Path
from datetime import datetime

# Ajouter le répertoire parent au path pour importer l'application
sys.path.insert(0, str(Path(__file__).parent.parent))

from app import create_app, db
from app.utils import detect_am2315
from app.models import Setting

app = create_app()

print("=" * 60)
print("Diagnostic AM2315")
print("=" * 60)

with app.app_context():
    # Afficher la configuration
    print("\n1. Configuration:")
    setting = Setting.query.filter_by(key="Sensor_AM2315_Address").first()
    if setting:
        print(f"   Adresse I2C configurée: {setting.value}")
    else:
        print("   Adresse I2C: non configurée (utilisera 0x5C par défaut)")
    
    setting_type = Setting.query.filter_by(key="Sensor_AM2315_Type").first()
    if setting_type:
        print(f"   Type de capteur: {setting_type.value}")
    
    # Tester la détection
    print("\n2. Test de détection:")
    try:
        status = detect_am2315()
        print(f"   Statut: {status.get('status')}")
        print(f"   Message: {status.get('message')}")
        details = status.get('details', {})
        if details:
            print(f"   Détails: {details}")
            if 'temperature' in details and 'humidity' in details:
                print(f"   ✓ Température: {details['temperature']}°C")
                print(f"   ✓ Humidité: {details['humidity']}%")
            else:
                print("   ✗ Aucune mesure disponible")
    except Exception as exc:
        print(f"   ✗ Erreur: {exc}")
        import traceback
        traceback.print_exc()
    
    # Tester directement le driver AM2315
    print("\n3. Test direct du driver AM2315:")
    try:
        from app.hardware.AM2315 import AM2315
        
        # Lire l'adresse depuis les paramètres
        address = 0x5C
        setting = Setting.query.filter_by(key="Sensor_AM2315_Address").first()
        if setting and setting.value:
            addr_str = setting.value.strip()
            try:
                if addr_str.startswith("0x") or addr_str.startswith("0X"):
                    address = int(addr_str, 16)
                else:
                    address = int(addr_str, 16) if all(c in "0123456789ABCDEFabcdef" for c in addr_str) else int(addr_str)
            except (ValueError, TypeError):
                pass
        
        print(f"   Tentative d'initialisation avec adresse {hex(address)}...")
        try:
            sensor = AM2315(address=address)
        except TypeError:
            try:
                sensor = AM2315(address=address, busnum=1)
            except TypeError:
                sensor = AM2315()
        
        print("   Tentative de lecture...")
        try:
            humidity, temperature = sensor.read_humidity_temperature()
            print(f"   ✓ Température: {temperature}°C")
            print(f"   ✓ Humidité: {humidity}%")
            print("   ✓ Lecture réussie!")
        except Exception as exc:
            print(f"   ✗ Erreur de lecture: {exc}")
            import traceback
            traceback.print_exc()
            
            # Essayer séparément
            print("\n   Tentative de lecture séparée...")
            try:
                temp = sensor.read_temperature()
                print(f"   ✓ Température: {temp}°C")
            except Exception as exc2:
                print(f"   ✗ Erreur lecture température: {exc2}")
            
            try:
                hum = sensor.read_humidity()
                print(f"   ✓ Humidité: {hum}%")
            except Exception as exc2:
                print(f"   ✗ Erreur lecture humidité: {exc2}")
                
    except ImportError as exc:
        print(f"   ✗ Impossible d'importer AM2315: {exc}")
    except Exception as exc:
        print(f"   ✗ Erreur: {exc}")
        import traceback
        traceback.print_exc()
    
    # Vérifier le bus I2C
    print("\n4. Vérification du bus I2C:")
    import os
    if os.path.exists("/dev/i2c-1"):
        print("   ✓ /dev/i2c-1 existe")
        try:
            with open("/dev/i2c-1", "rb") as f:
                print("   ✓ /dev/i2c-1 est accessible en lecture")
        except PermissionError:
            print("   ✗ Permission refusée pour /dev/i2c-1 (besoin de sudo ou groupe i2c)")
        except Exception as exc:
            print(f"   ✗ Erreur d'accès: {exc}")
    else:
        print("   ✗ /dev/i2c-1 n'existe pas")
    
    if os.path.exists("/dev/i2c-0"):
        print("   ✓ /dev/i2c-0 existe")
    else:
        print("   - /dev/i2c-0 n'existe pas (normal sur Raspberry Pi)")
    
    # Vérifier si le capteur est détecté sur le bus I2C
    print("\n5. Détection du capteur sur le bus I2C:")
    try:
        import subprocess
        result = subprocess.run(['i2cdetect', '-y', '1'], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            print("   Résultat de i2cdetect -y 1:")
            print("   " + "\n   ".join(result.stdout.split('\n')[:10]))
            if '5c' in result.stdout.lower() or '5C' in result.stdout:
                print("   ✓ Capteur détecté à l'adresse 0x5C")
            else:
                print("   ✗ Aucun capteur détecté à l'adresse 0x5C")
                print("   → Le capteur peut être déconnecté ou à une autre adresse")
        else:
            print(f"   ✗ Erreur i2cdetect: {result.stderr}")
    except FileNotFoundError:
        print("   - i2cdetect non disponible (installez i2c-tools)")
    except subprocess.TimeoutExpired:
        print("   ✗ Timeout lors de la détection I2C")
    except Exception as exc:
        print(f"   ✗ Erreur: {exc}")
    
    # Test avec retry et délais plus longs
    print("\n6. Test avec retry amélioré:")
    try:
        from app.hardware.AM2315 import AM2315
        import time
        
        address = 0x5C
        setting = Setting.query.filter_by(key="Sensor_AM2315_Address").first()
        if setting and setting.value:
            addr_str = setting.value.strip()
            try:
                if addr_str.startswith("0x") or addr_str.startswith("0X"):
                    address = int(addr_str, 16)
                else:
                    address = int(addr_str, 16) if all(c in "0123456789ABCDEFabcdef" for c in addr_str) else int(addr_str)
            except (ValueError, TypeError):
                pass
        
        print(f"   Initialisation du capteur (adresse {hex(address)})...")
        try:
            sensor = AM2315(address=address)
        except TypeError:
            try:
                sensor = AM2315(address=address, busnum=1)
            except TypeError:
                sensor = AM2315()
        
        print("   Attente de 2 secondes pour laisser le capteur se réveiller...")
        time.sleep(2)
        
        print("   Tentative de lecture avec retry...")
        for attempt in range(3):
            try:
                print(f"   Tentative {attempt + 1}/3...")
                humidity, temperature = sensor.read_humidity_temperature()
                print(f"   ✓ SUCCÈS! Température: {temperature}°C, Humidité: {humidity}%")
                break
            except RuntimeError as exc:
                print(f"   ✗ Tentative {attempt + 1} échouée: {exc}")
                if attempt < 2:
                    print(f"   Attente de 3 secondes avant la prochaine tentative...")
                    time.sleep(3)
                else:
                    print("   ✗ Toutes les tentatives ont échoué")
                    print("   → Le capteur ne répond pas. Vérifiez:")
                    print("     - Le câblage I2C (SDA, SCL, VCC, GND)")
                    print("     - Que le capteur est alimenté")
                    print("     - Que le bus I2C est activé (raspi-config)")
                    print("     - Que l'adresse I2C est correcte (0x5C)")
            except Exception as exc:
                print(f"   ✗ Erreur inattendue: {exc}")
                import traceback
                traceback.print_exc()
                break
    except Exception as exc:
        print(f"   ✗ Erreur lors du test: {exc}")
        import traceback
        traceback.print_exc()

print("\n" + "=" * 60)
print("Diagnostic terminé")
print("=" * 60)

