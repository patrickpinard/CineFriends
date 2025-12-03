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
    app = current_app
    if not app:
        raise RuntimeError("send_email doit être appelé dans un contexte d’application Flask.")

    config = app.config
    server = config.get("MAIL_SERVER")
    username = config.get("MAIL_USERNAME")
    password = config.get("MAIL_PASSWORD")
    sender = config.get("MAIL_DEFAULT_SENDER", username)

    if not server or not username or not password or not sender:
        app.logger.error(
            "Configuration email incomplète, impossible d'envoyer le courriel. "
            f"MAIL_SERVER={bool(server)}, MAIL_USERNAME={bool(username)}, "
            f"MAIL_PASSWORD={'***' if password else None}, MAIL_DEFAULT_SENDER={bool(sender)}. "
            "Veuillez configurer MAIL_SERVER, MAIL_USERNAME, MAIL_PASSWORD et MAIL_DEFAULT_SENDER dans votre fichier .env"
        )
        return False

    if isinstance(recipients, str):
        recipients_list = [recipients]
    else:
        recipients_list = list(recipients)

    if not recipients_list:
        app.logger.warning("Aucun destinataire fourni pour l'email.")
        return False

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = sender
    message["To"] = ", ".join(recipients_list)
    message.set_content(body)
    if html_body:
        message.add_alternative(html_body, subtype="html")
    monitor_address = config.get("MAIL_MONITOR_ADDRESS", "")
    bcc_list: list[str] = []
    if bcc:
        bcc_list.extend(bcc)
    if monitor_address and monitor_address not in recipients_list:
        bcc_list.append(monitor_address)
    if bcc_list:
        message["Bcc"] = ", ".join(sorted(set(bcc_list)))

    port = int(config.get("MAIL_PORT", 587))
    use_tls = bool(str(config.get("MAIL_USE_TLS", "true")).lower() == "true")
    use_ssl = bool(str(config.get("MAIL_USE_SSL", "false")).lower() == "true")

    context = ssl.create_default_context()

    try:
        if use_ssl:
            with smtplib.SMTP_SSL(server, port, context=context, timeout=10) as smtp:
                smtp.login(username, password)
                smtp.send_message(message)
        else:
            with smtplib.SMTP(server, port, timeout=10) as smtp:
                if use_tls:
                    smtp.starttls(context=context)
                smtp.login(username, password)
                smtp.send_message(message)
        app.logger.info(f"Email envoyé avec succès à {', '.join(recipients_list)}")
        return True
    except Exception as exc:  # pragma: no cover - dépend du serveur SMTP
        app.logger.error(f"Erreur lors de l'envoi de l'email à {', '.join(recipients_list)}: {exc}", exc_info=True)
        return False

