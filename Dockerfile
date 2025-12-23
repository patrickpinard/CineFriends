# Dockerfile pour TemplateApp
# Multi-stage build pour optimiser la taille de l'image

# Stage 1: Build
FROM python:3.11-slim as builder

WORKDIR /build

# Installer les dépendances système nécessaires
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copier et installer les dépendances Python
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Stage 2: Runtime
FROM python:3.11-slim

WORKDIR /app

# Créer un utilisateur non-root pour la sécurité
RUN useradd -m -u 1000 appuser && \
    mkdir -p /app/instance /app/logs /app/app/static/uploads && \
    chown -R appuser:appuser /app

# Copier les dépendances Python depuis le builder
COPY --from=builder /root/.local /home/appuser/.local

# Copier le code de l'application
COPY --chown=appuser:appuser . .

# Ajouter le répertoire local au PATH
ENV PATH=/home/appuser/.local/bin:$PATH
ENV PYTHONUNBUFFERED=1

# Passer à l'utilisateur non-root
USER appuser

# Exposer le port
EXPOSE 8080

# Variables d'environnement par défaut
ENV FLASK_ENV=production
ENV PYTHONPATH=/app

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8080/health')" || exit 1

# Commande par défaut (peut être surchargée)
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "4", "--worker-class", "sync", "--timeout", "120", "--access-logfile", "-", "--error-logfile", "-", "run:app"]

