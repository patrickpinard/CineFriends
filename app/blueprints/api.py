from datetime import datetime

from flask import Blueprint, current_app, jsonify, request, url_for
from flask_login import current_user, login_required

from app import db
from app.hardware.gpio_controller import get_configured_relay_pins
from app.helpers import _collect_relay_states_with_fallback, _get_sensor_highlights
from app.models import Notification

api_bp = Blueprint("api", __name__)


@api_bp.route("/api/dashboard/highlights")
@login_required
def dashboard_highlights_api():
    cards = _get_sensor_highlights()
    return jsonify({"cards": cards})


@api_bp.route("/api/relays/states")
@login_required
def relays_states_api():
    relay_pins = get_configured_relay_pins()
    states = _collect_relay_states_with_fallback(relay_pins)
    return jsonify({"states": states, "timestamp": datetime.utcnow().isoformat()})


@api_bp.route("/api/server-time")
@login_required
def server_time():
    """Retourne l'heure actuelle du serveur (Raspberry Pi) en heure locale"""
    # Utiliser datetime.now() pour obtenir l'heure locale du système (Raspberry Pi)
    server_now_local = datetime.now()
    server_now_utc = datetime.utcnow()
    
    return jsonify({
        "timestamp": server_now_local.isoformat(),
        "utc": server_now_utc.isoformat(),
        "local": server_now_local.strftime("%H:%M:%S"),
        "date": server_now_local.strftime("%d/%m/%Y"),
        "timezone_offset": (server_now_local - server_now_utc).total_seconds() / 3600,  # Offset en heures
    })


@api_bp.route("/notifications/read", methods=["POST"])
@login_required
def notifications_mark_read():
    ids = request.json.get("ids") if request.is_json else None  # type: ignore[attr-defined]
    query = Notification.query.filter(
        (Notification.user_id == current_user.id)
        | (Notification.audience == "global")
        | ((Notification.audience == "admin") & (current_user.role == "admin"))
    )
    if ids:
        query = query.filter(Notification.id.in_(ids))
    for notif in query:
        notif.read = True
        db.session.add(notif)
    db.session.commit()
    return jsonify({"status": "ok"})


@api_bp.route("/notifications/clear", methods=["POST"])
@login_required
def notifications_clear():
    payload = request.get_json(silent=True) or {}
    ids = payload.get("ids")

    query = Notification.query.filter(
        (Notification.user_id == current_user.id)
        | (Notification.audience == "global")
        | ((Notification.audience == "admin") & (current_user.role == "admin"))
    )

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


@api_bp.route("/manifest.json")
def manifest():
    manifest_data = {
        "name": "Dashboard Automatisation",
        "short_name": "Dashboard",
        "start_url": "/",
        "display": "standalone",
        "background_color": "#0f172a",
        "theme_color": "#0f172a",
        "lang": "fr",
        "icons": [
            {
                "src": url_for("static", filename="img/icon-128.png", _external=True),
                "sizes": "128x128",
                "type": "image/png"
            },
            {
                "src": url_for("static", filename="img/192.png", _external=True),
                "sizes": "192x192",
                "type": "image/png"
            },
            {
                "src": url_for("static", filename="img/256.png", _external=True),
                "sizes": "256x256",
                "type": "image/png"
            },
            {
                "src": url_for("static", filename="img/icon-512.png", _external=True),
                "sizes": "512x512",
                "type": "image/png"
            }
        ]
    }
    return jsonify(manifest_data)


@api_bp.route("/service-worker.js")
def service_worker():
    response = current_app.response_class(
        current_app.open_resource("static/js/service-worker.js").read(),
        mimetype="application/javascript",
    )
    response.cache_control.max_age = 0
    return response
