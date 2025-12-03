"""
Module d'envoi d'emails pour l'application TemplateApp.

Ce module fournit une fonction pour envoyer des emails via SMTP avec support
pour TLS/SSL, emails HTML et texte, et gestion des erreurs.

Fonctionnalités :
- Envoi d'emails multipart (HTML et texte)
- Support TLS et SSL
- Gestion automatique des destinataires en BCC (monitoring)
- Logging détaillé des succès et erreurs
- Validation de la configuration avant envoi
- Retour booléen pour indiquer le succès/échec

Configuration requise (variables d'environnement) :
- MAIL_SERVER : Serveur SMTP (ex: smtp.gmail.com)
- MAIL_PORT : Port SMTP (défaut: 587)
- MAIL_USERNAME : Nom d'utilisateur SMTP
- MAIL_PASSWORD : Mot de passe SMTP
- MAIL_DEFAULT_SENDER : Expéditeur par défaut
- MAIL_USE_TLS : Utiliser TLS (true/false, défaut: true)
- MAIL_USE_SSL : Utiliser SSL (true/false, défaut: false)
- MAIL_MONITOR_ADDRESS : Adresse email pour copie de monitoring (optionnel)

Exemple d'utilisation :
    from app.mailer import send_email
    
    success = send_email(
        subject="Bienvenue",
        recipients="user@example.com",
        body="Message texte",
        html_body="<p>Message HTML</p>"
    )
    
    if success:
        print("Email envoyé avec succès")
    else:
        print("Échec de l'envoi de l'email")
"""

from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage
from typing import Iterable, Sequence

from flask import current_app


def send_email(
    subject: str,
    recipients: str | Iterable[str],
    body: str,
    html_body: str | None = None,
    bcc: Sequence[str] | None = None,
) -> bool:
    """
    Envoie un email via SMTP avec support TLS/SSL.
    
    Cette fonction gère l'envoi d'emails multipart (HTML et texte) via SMTP.
    Elle lit la configuration depuis `app.config` et gère automatiquement
    les erreurs avec logging détaillé.
    
    Args:
        subject: Sujet de l'email (requis).
        recipients: Destinataire(s) de l'email. Peut être :
            - Une chaîne de caractères (un seul destinataire)
            - Un itérable de chaînes (plusieurs destinataires)
        body: Corps texte de l'email (requis). Version texte brut du message.
        html_body: Corps HTML de l'email (optionnel). Si fourni, l'email sera
            envoyé en format multipart avec les deux versions (texte et HTML).
        bcc: Liste de destinataires en copie cachée (optionnel). Ces adresses
            recevront l'email sans être visibles par les autres destinataires.
    
    Returns:
        bool: True si l'email a été envoyé avec succès, False sinon.
            Retourne False dans les cas suivants :
            - Configuration email incomplète
            - Aucun destinataire fourni
            - Erreur lors de la connexion SMTP
            - Erreur lors de l'authentification
            - Erreur lors de l'envoi
    
    Raises:
        RuntimeError: Si la fonction est appelée en dehors d'un contexte
            d'application Flask (pas de `current_app` disponible).
    
    Configuration SMTP :
        La fonction lit les paramètres suivants depuis `app.config` :
        - MAIL_SERVER : Serveur SMTP (requis)
        - MAIL_PORT : Port SMTP (défaut: 587)
        - MAIL_USERNAME : Nom d'utilisateur SMTP (requis)
        - MAIL_PASSWORD : Mot de passe SMTP (requis)
        - MAIL_DEFAULT_SENDER : Expéditeur par défaut (requis, fallback: MAIL_USERNAME)
        - MAIL_USE_TLS : Utiliser TLS (défaut: true)
        - MAIL_USE_SSL : Utiliser SSL (défaut: false)
        - MAIL_MONITOR_ADDRESS : Adresse de monitoring en BCC (optionnel)
    
    Gestion des erreurs :
        - Les erreurs de configuration sont loggées avec le niveau ERROR
        - Les erreurs d'envoi sont loggées avec le niveau ERROR et incluent
          la trace complète (exc_info=True)
        - Les succès sont loggés avec le niveau INFO
        - La fonction ne lève jamais d'exception, elle retourne False en cas d'erreur
    
    Sécurité :
        - Utilise SSL/TLS pour chiffrer la connexion SMTP
        - Le mot de passe n'est jamais loggé (masqué dans les logs)
        - Utilise un contexte SSL par défaut (certificats vérifiés)
        - Timeout de 10 secondes pour éviter les blocages
    
    Exemple d'utilisation :
        # Email simple texte
        send_email(
            subject="Notification",
            recipients="user@example.com",
            body="Votre compte a été activé."
        )
        
        # Email HTML et texte
        send_email(
            subject="Bienvenue",
            recipients=["user1@example.com", "user2@example.com"],
            body="Message texte brut",
            html_body="<h1>Message HTML</h1><p>Contenu formaté</p>"
        )
        
        # Email avec BCC
        send_email(
            subject="Rapport",
            recipients="manager@example.com",
            body="Rapport mensuel",
            bcc=["archive@example.com"]
        )
    
    Notes :
        - Si MAIL_MONITOR_ADDRESS est configuré, cette adresse sera
          automatiquement ajoutée en BCC (sauf si elle est déjà dans les
          destinataires principaux)
        - Les adresses BCC sont triées et dédupliquées automatiquement
        - Le format multipart (HTML + texte) est utilisé uniquement si
          html_body est fourni
        - La fonction doit être appelée dans un contexte de requête Flask
          (avec current_app disponible)
    """
    app = current_app
    if not app:
        raise RuntimeError("send_email doit être appelé dans un contexte d'application Flask.")

    # Récupération de la configuration SMTP depuis app.config
    config = app.config
    server = config.get("MAIL_SERVER")
    username = config.get("MAIL_USERNAME")
    password = config.get("MAIL_PASSWORD")
    sender = config.get("MAIL_DEFAULT_SENDER", username)

    # Validation de la configuration requise
    if not server or not username or not password or not sender:
        app.logger.error(
            "Configuration email incomplète, impossible d'envoyer le courriel. "
            f"MAIL_SERVER={bool(server)}, MAIL_USERNAME={bool(username)}, "
            f"MAIL_PASSWORD={'***' if password else None}, MAIL_DEFAULT_SENDER={bool(sender)}. "
            "Veuillez configurer MAIL_SERVER, MAIL_USERNAME, MAIL_PASSWORD et MAIL_DEFAULT_SENDER dans votre fichier .env"
        )
        return False

    # Normalisation des destinataires en liste
    if isinstance(recipients, str):
        recipients_list = [recipients]
    else:
        recipients_list = list(recipients)

    # Validation de la présence de destinataires
    if not recipients_list:
        app.logger.warning("Aucun destinataire fourni pour l'email.")
        return False

    # Création du message email
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = sender
    message["To"] = ", ".join(recipients_list)
    message.set_content(body)  # Version texte
    
    # Ajout de la version HTML si fournie (format multipart)
    if html_body:
        message.add_alternative(html_body, subtype="html")
    
    # Gestion des destinataires en BCC (copie cachée)
    monitor_address = config.get("MAIL_MONITOR_ADDRESS", "")
    bcc_list: list[str] = []
    if bcc:
        bcc_list.extend(bcc)
    # Ajout automatique de l'adresse de monitoring si configurée
    if monitor_address and monitor_address not in recipients_list:
        bcc_list.append(monitor_address)
    if bcc_list:
        # Tri et déduplication des adresses BCC
        message["Bcc"] = ", ".join(sorted(set(bcc_list)))

    # Configuration de la connexion SMTP
    port = int(config.get("MAIL_PORT", 587))
    use_tls = bool(str(config.get("MAIL_USE_TLS", "true")).lower() == "true")
    use_ssl = bool(str(config.get("MAIL_USE_SSL", "false")).lower() == "true")

    # Création du contexte SSL pour le chiffrement
    context = ssl.create_default_context()

    # Tentative d'envoi de l'email
    try:
        if use_ssl:
            # Connexion SMTP avec SSL (port généralement 465)
            with smtplib.SMTP_SSL(server, port, context=context, timeout=10) as smtp:
                smtp.login(username, password)
                smtp.send_message(message)
        else:
            # Connexion SMTP standard avec TLS optionnel (port généralement 587)
            with smtplib.SMTP(server, port, timeout=10) as smtp:
                if use_tls:
                    smtp.starttls(context=context)
                smtp.login(username, password)
                smtp.send_message(message)
        
        # Succès : log et retour True
        app.logger.info(f"Email envoyé avec succès à {', '.join(recipients_list)}")
        return True
    except Exception as exc:  # pragma: no cover - dépend du serveur SMTP
        # Erreur : log détaillé avec traceback et retour False
        app.logger.error(f"Erreur lors de l'envoi de l'email à {', '.join(recipients_list)}: {exc}", exc_info=True)
        return False

