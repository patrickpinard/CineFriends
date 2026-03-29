"""API de gestion des notifications utilisateur."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from flask import jsonify, request
from flask_login import current_user, login_required

from .. import db
from ..models import Notification
from . import main_bp


@main_bp.route("/api/notifications/broadcasts")
@login_required
def notifications_broadcasts():
    """Retourne les notifications broadcast des 30 derniers jours (pour affichage modal côté client)."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    broadcasts = Notification.query.filter(
        Notification.audience == "global",
        Notification.created_at >= cutoff,
    ).order_by(Notification.created_at.asc()).limit(20).all()
    return jsonify([
        {"id": n.id, "title": n.title, "message": n.message, "level": n.level or "info"}
        for n in broadcasts
    ])


def _user_notifications_query():
    """Retourne la query de base filtrant les notifications accessibles à l'utilisateur."""
    return Notification.query.filter(
        (Notification.user_id == current_user.id)
        | (Notification.audience == "global")
        | ((Notification.audience == "admin") & (current_user.role == "admin"))
    )


@main_bp.route("/notifications/read", methods=["POST"])
@login_required
def notifications_mark_read():
    ids = request.json.get("ids") if request.is_json else None  # type: ignore[attr-defined]
    query = _user_notifications_query()
    if ids:
        query = query.filter(Notification.id.in_(ids))
    for notif in query:
        notif.read = True
        db.session.add(notif)
    db.session.commit()
    return jsonify({"status": "ok"})


@main_bp.route("/notifications/clear", methods=["POST"])
@login_required
def notifications_clear():
    payload = request.get_json(silent=True) or {}
    ids = payload.get("ids")

    query = _user_notifications_query()
    if ids:
        try:
            ids = [int(_id) for _id in ids]
        except (TypeError, ValueError):
            ids = []
        if ids:
            query = query.filter(Notification.id.in_(ids))

    notifications = query.all()
    cleared_ids: list[int] = []

    for notif in notifications:
        cleared_ids.append(notif.id)
        if notif.user_id == current_user.id:
            db.session.delete(notif)
        else:
            notif.read = True
            db.session.add(notif)

    db.session.commit()
    return jsonify({"status": "ok", "cleared": cleared_ids})
