#!/bin/bash

set -euo pipefail

SERVICE_NAME="dashboard.service"

echo "Rechargement des unités systemd..."
sudo systemctl daemon-reload

# Vérification de l'exécutable
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}"
if [[ -f "$SERVICE_FILE" ]]; then
    EXEC_PATH=$(grep -E '^ExecStart=' "$SERVICE_FILE" | head -n1 | cut -d'=' -f2 | awk '{print $1}')
    if [[ -n "$EXEC_PATH" && ! -x "$EXEC_PATH" ]]; then
        echo "Attention: l'exécutable indiqué dans ExecStart (${EXEC_PATH}) est introuvable ou non exécutable."
        echo "Vérifiez ${SERVICE_FILE}."
    fi
fi

echo "Arrêt de ${SERVICE_NAME}..."
sudo systemctl stop "${SERVICE_NAME}"

echo "Démarrage de ${SERVICE_NAME}..."
if ! sudo systemctl start "${SERVICE_NAME}"; then
    echo "Échec du démarrage de ${SERVICE_NAME}."
    sudo journalctl -u "${SERVICE_NAME}" -n 50 --no-pager
    exit 1
fi

sudo systemctl status "${SERVICE_NAME}" --no-pager --lines=20

