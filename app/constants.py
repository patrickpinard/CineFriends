from __future__ import annotations

METRIC_LABELS = {
    "temperature": "Température",
    "humidity": "Humidité",
}

RELAY_NAME_KEYS = {
    1: "Relay_Name_Ch1",
    2: "Relay_Name_Ch2",
    3: "Relay_Name_Ch3",
}

SENSOR_HIGHLIGHT_DEFINITIONS = [
    {
        "sensor_type": "ds18b20",
        "metric": "temperature",
        "title": "Température DS18B20",
        "subtitle_key": "ds18b20",
        "default_unit": "°C",
        "icon": "temperature",
    },
    {
        "sensor_type": "am2315",
        "metric": "temperature",
        "title": "Température AM2315",
        "subtitle_key": "am2315",
        "default_unit": "°C",
        "icon": "temperature",
    },
    {
        "sensor_type": "am2315",
        "metric": "humidity",
        "title": "Humidité AM2315",
        "subtitle_key": "am2315",
        "default_unit": "%",
        "icon": "humidity",
    },
]

HARDWARE_SETTING_GROUPS = [
    {
        "id": "actuators",
        "title": "Actionneurs • Carte relais",
        "subtitle": "Définissez les broches BCM utilisées par les trois relais pilotés via RPi.GPIO.",
        "items": [
            {
                "key": "Relay_Ch1",
                "label": "Relais canal 1 (GPIO BCM)",
                "default": "26",
                "description": "Broche BCM pour le premier relais (CH1).",
                "group": "relay_1",
                "group_title": "Relais 1",
                "group_subtitle": "Configuration du canal 1",
            },
            {
                "key": "Relay_Name_Ch1",
                "label": "Nom du relais 1",
                "default": "Relais 1",
                "description": "Nom affiché dans le dashboard et les règles.",
                "group": "relay_1",
            },
            {
                "key": "Relay_Ch2",
                "label": "Relais canal 2 (GPIO BCM)",
                "default": "20",
                "description": "Broche BCM pour le deuxième relais (CH2).",
                "group": "relay_2",
                "group_title": "Relais 2",
                "group_subtitle": "Configuration du canal 2",
            },
            {
                "key": "Relay_Name_Ch2",
                "label": "Nom du relais 2",
                "default": "Relais 2",
                "description": "Nom affiché dans le dashboard et les règles.",
                "group": "relay_2",
            },
            {
                "key": "Relay_Ch3",
                "label": "Relais canal 3 (GPIO BCM)",
                "default": "21",
                "description": "Broche BCM pour le troisième relais (CH3).",
                "group": "relay_3",
                "group_title": "Relais 3",
                "group_subtitle": "Configuration du canal 3",
            },
            {
                "key": "Relay_Name_Ch3",
                "label": "Nom du relais 3",
                "default": "Relais 3",
                "description": "Nom affiché dans le dashboard et les règles.",
                "group": "relay_3",
            },
        ],
    },
    {
        "id": "sensors",
        "title": "Capteurs • Température & humidité",
        "subtitle": "Paramétrez les sondes connectées au Raspberry Pi.",
        "items": [
            {
                "key": "Sensor_DS18B20_Interface",
                "label": "Sonde intérieure DS18B20",
                "default": "w1",
                "description": "Interface utilisée pour la sonde 1-Wire (DS18B20).",
                "group": "sensor_ds18b20",
                "group_title": "Sonde DS18B20",
                "group_subtitle": "Capteur de température 1-Wire",
            },
            {
                "key": "Sensor_AM2315_Type",
                "label": "Sonde extérieure AM2315",
                "default": "AM2315",
                "description": "Type de capteur utilisé (AM2315).",
                "group": "sensor_am2315",
                "group_title": "Sonde AM2315",
                "group_subtitle": "Capteur I²C Température/Humidité",
            },
            {
                "key": "Sensor_AM2315_Address",
                "label": "Adresse I²C AM2315",
                "default": "0x5C",
                "description": "Adresse I²C par défaut du capteur AM2315.",
                "group": "sensor_am2315",
            },
        ],
    },
    {
        "id": "system",
        "title": "Système • Collecte & LCD",
        "subtitle": "Options générales du système.",
        "items": [
            {
                "key": "Sensor_Poll_Interval_Minutes",
                "label": "Intervalle de collecte (minutes)",
                "default": "15",
                "description": "Fréquence d'enregistrement des mesures (min 1, max 1440).",
            },
            {
                "key": "LCD_Enabled",
                "label": "Activer l'écran LCD",
                "default": "0",
                "description": "Si activé, les informations seront affichées sur l'écran Grove LCD RGB.",
            },
        ],
    },
]
