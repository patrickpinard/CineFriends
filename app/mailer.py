"""Envoi d'emails SMTP pour TemplateApp."""

from __future__ import annotations

import smtplib
import ssl
import threading
from email.message import EmailMessage
from typing import Iterable, Sequence

from flask import current_app


def send_email(
    subject: str,
    recipients: str | Iterable[str],
    body: str,
    html_body: str | None = None,
    bcc: Sequence[str] | None = None,
    async_send: bool = True,
) -> bool:
    """
    Envoie un email via SMTP (asynchrone par défaut).

    Args:
        subject: Sujet de l'email.
        recipients: Destinataire(s) — chaîne ou itérable.
        body: Corps texte brut.
        html_body: Corps HTML (optionnel, active le multipart).
        bcc: Adresses en copie cachée (optionnel).
        async_send: Si True (défaut), envoie en arrière-plan sans bloquer la requête.

    Returns:
        True si l'envoi est lancé (async) ou réussi (sync), False si la config est invalide.
    """
    app = current_app._get_current_object()  # Référence réelle pour les threads
    config = app.config

    server = config.get("MAIL_SERVER")
    username = config.get("MAIL_USERNAME")
    password = config.get("MAIL_PASSWORD")
    sender = config.get("MAIL_DEFAULT_SENDER", username)

    if not all([server, username, password, sender]):
        app.logger.error(
            "Configuration email incomplète — vérifiez MAIL_SERVER, MAIL_USERNAME, "
            "MAIL_PASSWORD et MAIL_DEFAULT_SENDER dans .env"
        )
        return False

    recipients_list = [recipients] if isinstance(recipients, str) else list(recipients)
    if not recipients_list:
        app.logger.warning("Aucun destinataire fourni.")
        return False

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = ", ".join(recipients_list)
    msg.set_content(body)
    if html_body:
        msg.add_alternative(html_body, subtype="html")

    monitor = config.get("MAIL_MONITOR_ADDRESS", "")
    bcc_list: list[str] = list(bcc or [])
    if monitor and monitor not in recipients_list:
        bcc_list.append(monitor)
    if bcc_list:
        msg["Bcc"] = ", ".join(sorted(set(bcc_list)))

    port = int(config.get("MAIL_PORT", 587))
    use_tls = str(config.get("MAIL_USE_TLS", "true")).lower() == "true"
    use_ssl = str(config.get("MAIL_USE_SSL", "false")).lower() == "true"

    def _do_send() -> None:
        context = ssl.create_default_context()
        try:
            if use_ssl:
                with smtplib.SMTP_SSL(server, port, context=context, timeout=10) as smtp:
                    smtp.login(username, password)
                    smtp.send_message(msg)
            else:
                with smtplib.SMTP(server, port, timeout=10) as smtp:
                    if use_tls:
                        smtp.starttls(context=context)
                    smtp.login(username, password)
                    smtp.send_message(msg)
            app.logger.info("Email envoyé à %s", ", ".join(recipients_list))
        except Exception as exc:
            app.logger.error(
                "Erreur envoi email à %s: %s", ", ".join(recipients_list), exc, exc_info=True
            )

    if async_send:
        t = threading.Thread(target=_do_send, daemon=True)
        t.start()
        return True

    _do_send()
    return True
