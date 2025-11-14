#!/bin/bash

set -euo pipefail

SERVICE_NAME="dashboard.service"

echo "Arrêt de ${SERVICE_NAME}..."
sudo systemctl stop "${SERVICE_NAME}"

echo "Redémarrage de ${SERVICE_NAME}..."
sudo systemctl start "${SERVICE_NAME}"

sudo systemctl status "${SERVICE_NAME}" --no-pager --lines=20

