"""
Package : app.hardware
Objectif : Rassembler les pilotes matériels et helpers GPIO utilisés par le Dashboard.
Contenu :
    - `AM2315` : lecture du capteur température/humidité I²C.
    - `adasmbus` : implémentation Python de SMBus compatible avec le matériel client.
    - `gpio_controller` : pilotage des relais via RPi.GPIO avec reconfiguration automatique.
"""


