#!/usr/bin/env python3
"""
Script pour désinstaller tous les packages pip (sauf pip, setuptools, wheel)
"""
import subprocess
import sys

# Packages à conserver
KEEP_PACKAGES = {'pip', 'setuptools', 'wheel'}

def get_installed_packages():
    """Récupère la liste des packages installés"""
    try:
        result = subprocess.run(
            [sys.executable, '-m', 'pip', 'list', '--format=freeze'],
            capture_output=True,
            text=True,
            check=True
        )
        packages = []
        for line in result.stdout.strip().split('\n'):
            if '==' in line:
                package_name = line.split('==')[0].strip()
                if package_name.lower() not in KEEP_PACKAGES:
                    packages.append(package_name)
        return packages
    except Exception as e:
        print(f"Erreur lors de la récupération des packages: {e}")
        return []

def uninstall_packages(packages):
    """Désinstalle les packages"""
    if not packages:
        print("Aucun package à désinstaller.")
        return
    
    print(f"\nPackages à désinstaller ({len(packages)}):")
    for pkg in packages:
        print(f"  - {pkg}")
    
    response = input("\nVoulez-vous vraiment désinstaller tous ces packages ? (oui/non): ")
    if response.lower() not in ['oui', 'o', 'yes', 'y']:
        print("Annulé.")
        return
    
    print("\nDésinstallation en cours...")
    for package in packages:
        try:
            subprocess.run(
                [sys.executable, '-m', 'pip', 'uninstall', '-y', package],
                check=True
            )
            print(f"✓ {package} désinstallé")
        except subprocess.CalledProcessError as e:
            print(f"✗ Erreur lors de la désinstallation de {package}: {e}")
    
    print("\nDésinstallation terminée.")

if __name__ == "__main__":
    print("=== Désinstallation de tous les packages pip ===")
    print(f"Python: {sys.executable}")
    print(f"Packages conservés: {', '.join(KEEP_PACKAGES)}")
    
    packages = get_installed_packages()
    uninstall_packages(packages)

