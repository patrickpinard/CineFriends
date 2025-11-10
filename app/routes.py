from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from typing import Generator

from flask import (Blueprint, Response, current_app, flash, jsonify, redirect,
                   render_template, request, url_for)
from flask_login import current_user, login_required
from urllib.parse import urlencode

from . import db
from .forms import AutomationRuleForm, ProfileForm, SettingForm
from .models import AutomationRule, JournalEntry, Notification, Setting, User
from .services import create_notification
from .utils import build_changes, build_hardware_overview, delete_avatar, save_avatar

try:
    import cv2  # type: ignore
except ImportError:  # pragma: no cover - dépendance optionnelle
    cv2 = None  # type: ignore


main_bp = Blueprint("main", __name__)


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
            },
            {
                "key": "Relay_Ch2",
                "label": "Relais canal 2 (GPIO BCM)",
                "default": "20",
                "description": "Broche BCM pour le deuxième relais (CH2).",
            },
            {
                "key": "Relay_Ch3",
                "label": "Relais canal 3 (GPIO BCM)",
                "default": "21",
                "description": "Broche BCM pour le troisième relais (CH3).",
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
                "label": "Sonde intérieure DS18B20 (interface)",
                "default": "w1",
                "description": "Interface utilisée pour la sonde 1-Wire (DS18B20).",
            },
            {
                "key": "Sensor_AM2315_Type",
                "label": "Sonde extérieure AM2315",
                "default": "AM2315",
                "description": "Identifiant du capteur I²C pour la température et l’humidité extérieures.",
            },
            {
                "key": "Sensor_AM2315_Address",
                "label": "Adresse I²C AM2315",
                "default": "0x5C",
                "description": "Adresse I²C par défaut du capteur AM2315.",
            },
        ],
    },
]


def _camera_stream() -> Generator[bytes, None, None]:
    if cv2 is None:
        current_app.logger.error("OpenCV n’est pas installé pour le streaming caméra.")
        raise RuntimeError("Camera indisponible")

    capture = cv2.VideoCapture(0)
    if not capture.isOpened():
        current_app.logger.error("Impossible d’ouvrir la caméra USB.")
        raise RuntimeError("Camera indisponible")

    try:
        while True:
            success, frame = capture.read()
            if not success:
                continue

            ret, buffer = cv2.imencode(".jpg", frame)
            if not ret:
                continue

            frame_bytes = buffer.tobytes()
            yield (b"--frame\r\n"
                   b"Content-Type: image/jpeg\r\n\r\n" + frame_bytes + b"\r\n")
    finally:
        capture.release()


@main_bp.route("/")
@login_required
def dashboard():
    rules_count = AutomationRule.query.count()
    journal_count = JournalEntry.query.count()
    today = datetime.utcnow().date()
    chart_labels = [(today - timedelta(days=i)).strftime('%d/%m') for i in range(6, -1, -1)]
    chart_temperatures = [21.5, 22.1, 20.8, 19.9, 21.2, 22.4, 21.0]
    chart_humidity = [48, 51, 55, 58, 53, 49, 52]
    return render_template(
        "dashboard/index.html",
        rules_count=rules_count,
        journal_count=journal_count,
        chart_labels=chart_labels,
        chart_temperatures=chart_temperatures,
        chart_humidity=chart_humidity,
    )


@main_bp.route("/automatisation", methods=["GET", "POST"])
@login_required
def automation():
    form = AutomationRuleForm()

    search = request.args.get("q", "").strip()
    owner_id = request.args.get("owner", "")
    sort = request.args.get("sort", "")

    query = AutomationRule.query.join(User)

    if search:
        like = f"%{search}%"
        query = query.filter(
            db.or_(
                AutomationRule.name.ilike(like),
                AutomationRule.trigger.ilike(like),
                AutomationRule.action.ilike(like),
            )
        )

    if owner_id.isdigit():
        query = query.filter(AutomationRule.owner_id == int(owner_id))

    if sort == "name":
        query = query.order_by(AutomationRule.name.asc())
    else:
        query = query.order_by(AutomationRule.created_at.desc())

    filters = {"q": search, "owner": owner_id, "sort": sort}
    filters_query = urlencode({k: v for k, v in filters.items() if v})

    if form.validate_on_submit():
        rule = AutomationRule(
            name=form.name.data,
            trigger=form.trigger.data,
            action=form.action.data,
            owner=current_user,
        )
        db.session.add(rule)
        db.session.add(JournalEntry(level="info", message=f"Nouvelle règle créée: {rule.name}"))
        db.session.commit()
        flash("Règle enregistrée.", "success")
        redirect_url = url_for("main.automation") + ("?" + filters_query if filters_query else "")
        return redirect(redirect_url)

    rules = query.all()
    return render_template(
        "dashboard/automation.html",
        form=form,
        rules=rules,
        filters=filters,
        filters_query=filters_query,
        form_action=url_for("main.automation") + ("?" + filters_query if filters_query else ""),
        form_title="Créer une règle",
        form_subtitle="Définissez les déclencheurs et actions pour automatiser vos scénarios.",
        submit_label="Enregistrer",
        cancel_url=None,
        editing_rule_id=None,
    )


@main_bp.route("/automatisation/<int:rule_id>/modifier", methods=["GET", "POST"])
@login_required
def edit_rule(rule_id: int):
    rule = AutomationRule.query.get_or_404(rule_id)
    if rule.owner != current_user and current_user.role != "admin":
        flash("Accès refusé.", "danger")
        return redirect(url_for("main.automation"))

    form = AutomationRuleForm(obj=rule)

    search = request.args.get("q", "").strip()
    owner_id = request.args.get("owner", "")
    sort = request.args.get("sort", "")
    query = AutomationRule.query.join(User)

    if search:
        like = f"%{search}%"
        query = query.filter(
            db.or_(
                AutomationRule.name.ilike(like),
                AutomationRule.trigger.ilike(like),
                AutomationRule.action.ilike(like),
            )
        )

    if owner_id.isdigit():
        query = query.filter(AutomationRule.owner_id == int(owner_id))

    if sort == "name":
        query = query.order_by(AutomationRule.name.asc())
    else:
        query = query.order_by(AutomationRule.created_at.desc())

    filters = {"q": search, "owner": owner_id, "sort": sort}
    filters_query = urlencode({k: v for k, v in filters.items() if v})

    if form.validate_on_submit():
        original = {"name": rule.name, "trigger": rule.trigger, "action": rule.action}
        updated = {
            "name": form.name.data,
            "trigger": form.trigger.data,
            "action": form.action.data,
        }
        changes = build_changes(original, updated, ["name", "trigger", "action"])

        rule.name = updated["name"]
        rule.trigger = updated["trigger"]
        rule.action = updated["action"]

        if changes:
            db.session.add(
                JournalEntry(
                    level="info",
                    message=f"Règle modifiée: {rule.name}",
                    details={
                        "entity": "automation_rule",
                        "rule_id": rule.id,
                        "changes": changes,
                        "updated_by": current_user.username,
                    },
                )
            )

        db.session.commit()
        flash("Règle mise à jour.", "success")
        redirect_url = url_for("main.automation") + ("?" + filters_query if filters_query else "")
        return redirect(redirect_url)

    rules = query.all()

    form_action = url_for("main.edit_rule", rule_id=rule.id)
    cancel_url = url_for("main.automation")
    if filters_query:
        form_action = f"{form_action}?{filters_query}"
        cancel_url = f"{cancel_url}?{filters_query}"

    return render_template(
        "dashboard/automation.html",
        form=form,
        rules=rules,
        filters=filters,
        filters_query=filters_query,
        form_action=form_action,
        form_title="Modifier la règle",
        form_subtitle=f"Dernière mise à jour le {rule.updated_at.strftime('%d/%m/%Y %H:%M') if rule.updated_at else rule.created_at.strftime('%d/%m/%Y %H:%M')}",
        submit_label="Mettre à jour",
        cancel_url=cancel_url,
        editing_rule_id=rule.id,
    )


@main_bp.route("/automatisation/<int:rule_id>/supprimer", methods=["POST"])
@login_required
def delete_rule(rule_id: int):
    rule = AutomationRule.query.get_or_404(rule_id)
    if rule.owner != current_user and current_user.role != "admin":
        flash("Accès refusé.", "danger")
        return redirect(url_for("main.automation"))
    db.session.delete(rule)
    db.session.add(JournalEntry(level="warning", message=f"Règle supprimée: {rule.name}"))
    db.session.commit()
    flash("Règle supprimée.", "info")
    return redirect(url_for("main.automation"))


@main_bp.route("/camera")
@login_required
def camera():
    return render_template("dashboard/camera.html")


@main_bp.route("/camera/flux")
@login_required
def camera_feed():
    try:
        return Response(_camera_stream(), mimetype="multipart/x-mixed-replace; boundary=frame")
    except RuntimeError:
        flash("Caméra indisponible.", "danger")
        return redirect(url_for("main.camera"))


@main_bp.route("/parametres", methods=["GET", "POST"])
@login_required
def settings():
    form = SettingForm()
    settings_list = Setting.query.order_by(Setting.key.asc()).all()
    settings_map = {setting.key: setting for setting in settings_list}

    initialized = False
    for key, default_value in ((item["key"], item["default"]) for group in HARDWARE_SETTING_GROUPS for item in group["items"]):
        if key not in settings_map:
            new_setting = Setting(key=key, value=default_value)
            db.session.add(new_setting)
            db.session.add(
                JournalEntry(
                    level="info",
                    message=f"Paramètre initialisé : {key}",
                    details={"value": default_value, "source": "default", "category": "hardware"},
                )
            )
            initialized = True

    if initialized:
        db.session.commit()
        settings_list = Setting.query.order_by(Setting.key.asc()).all()
        settings_map = {setting.key: setting for setting in settings_list}

    if request.method == "POST" and request.form.get("refresh_hardware") == "1":
        flash("Diagnostic matériel relancé.", "info")
        return redirect(url_for("main.settings"))

    if form.validate_on_submit():
        setting = Setting.query.filter_by(key=form.key.data).first()
        before_value = setting.value if setting else None
        if not setting:
            setting = Setting(key=form.key.data)
            db.session.add(setting)
        setting.value = form.value.data
        db.session.add(
            JournalEntry(
                level="info",
                message=f"Paramètre mis à jour : {setting.key}",
                details={"before": before_value, "after": form.value.data},
            )
        )
        db.session.commit()
        flash("Paramètre enregistré.", "success")
        return redirect(url_for("main.settings"))

    hardware_groups = []
    hardware_keys = set()
    for group in HARDWARE_SETTING_GROUPS:
        items = []
        for item in group["items"]:
            setting_obj = settings_map.get(item["key"])
            items.append(
                {
                    **item,
                    "value": setting_obj.value if setting_obj else item["default"],
                    "updated_at": setting_obj.updated_at if setting_obj else None,
                }
            )
            hardware_keys.add(item["key"])
        hardware_groups.append(
            {
                "id": group["id"],
                "title": group["title"],
                "subtitle": group["subtitle"],
                "parameters": items,
            }
        )

    def _get_int_value(key: str, fallback: int) -> int:
        value = settings_map.get(key).value if settings_map.get(key) else fallback
        try:
            return int(str(value).strip())
        except (ValueError, TypeError, AttributeError):
            return fallback

    relay_pins = [
        _get_int_value("Relay_Ch1", 26),
        _get_int_value("Relay_Ch2", 20),
        _get_int_value("Relay_Ch3", 21),
    ]

    hardware_status = build_hardware_overview(relay_pins)
    configured_values = {
        "relays": ", ".join(str(pin) for pin in relay_pins),
        "ds18b20": settings_map.get("Sensor_DS18B20_Interface").value if settings_map.get("Sensor_DS18B20_Interface") else "—",
        "am2315": settings_map.get("Sensor_AM2315_Type").value if settings_map.get("Sensor_AM2315_Type") else "—",
        "am2315_address": settings_map.get("Sensor_AM2315_Address").value if settings_map.get("Sensor_AM2315_Address") else "—",
    }

    for status in hardware_status:
        if status["id"] == "relays":
            status["configured"] = f"GPIO configurés : {configured_values['relays']}"
        elif status["id"] == "ds18b20":
            status["configured"] = f"Interface actuelle : {configured_values['ds18b20']}"
        elif status["id"] == "am2315":
            status["configured"] = f"Capteur : {configured_values['am2315']} @ {configured_values['am2315_address']}"

    return render_template(
        "dashboard/settings.html",
        form=form,
        hardware_groups=hardware_groups,
        hardware_status=hardware_status,
    )


@main_bp.route("/journal")
@login_required
def journal():
    if current_user.role != "admin":
        flash("Accès réservé à l’administrateur.", "danger")
        return redirect(url_for("main.dashboard"))
    search = request.args.get("q", "").strip()
    level = request.args.get("level", "")
    sort = request.args.get("sort", "recent")
    from_date = request.args.get("from", "")
    to_date = request.args.get("to", "")

    query = JournalEntry.query

    if search:
        like = f"%{search}%"
        query = query.filter(JournalEntry.message.ilike(like))

    if level in {"info", "warning", "danger"}:
        query = query.filter_by(level=level)

    if from_date:
        try:
            start = datetime.fromisoformat(from_date)
            query = query.filter(JournalEntry.created_at >= start)
        except ValueError:
            pass

    if to_date:
        try:
            end = datetime.fromisoformat(to_date)
            query = query.filter(JournalEntry.created_at <= end)
        except ValueError:
            pass

    if sort == "oldest":
        query = query.order_by(JournalEntry.created_at.asc())
    else:
        query = query.order_by(JournalEntry.created_at.desc())

    entries = query.all()
    detailed_entries = []
    for entry in entries:
        detail = entry.details or {}

        formatted = {
            "level": entry.level,
            "message": entry.message,
            "timestamp": entry.created_at,
            "detail": detail,
            "actors": detail.get("actors") if isinstance(detail.get("actors"), list) else None,
            "metadata": None,
        }

        metadata_items = []
        if isinstance(detail, dict):
            for key, value in detail.items():
                if key == "actors":
                    continue
                metadata_items.append({
                    "label": key.replace("_", " ").title(),
                    "value": value,
                })
        if metadata_items:
            formatted["metadata"] = metadata_items

        detailed_entries.append(formatted)
    return render_template(
        "dashboard/journal.html",
        entries=detailed_entries,
        filters={"q": search, "level": level, "from": from_date, "to": to_date},
    )


@main_bp.route("/journal/purge", methods=["POST"])
@login_required
def journal_purge():
    if current_user.role != "admin":
        flash("Accès réservé à l’administrateur.", "danger")
        return redirect(url_for("main.dashboard"))

    before_str = request.form.get("before")
    if not before_str:
        flash("Merci de sélectionner une date avant suppression.", "warning")
        return redirect(url_for("main.journal"))

    try:
        before_date = datetime.fromisoformat(before_str)
        threshold = datetime.combine(before_date.date(), datetime.max.time())
    except ValueError:
        flash("Date invalide.", "danger")
        return redirect(url_for("main.journal"))

    query = JournalEntry.query.filter(JournalEntry.created_at <= threshold)
    count = query.count()
    if count == 0:
        flash("Aucune entrée à supprimer pour cette date.", "info")
        return redirect(url_for("main.journal"))

    query.delete(synchronize_session=False)
    db.session.add(
        JournalEntry(
            level="warning",
            message="Purge du journal",
            details={
                "deleted_before": before_str,
                "deleted_count": count,
                "performed_by": current_user.username,
            },
        )
    )
    db.session.commit()
    flash(f"{count} entrée(s) supprimée(s) du journal.", "success")
    return redirect(url_for("main.journal"))


@main_bp.route("/profil", methods=["GET", "POST"])
@login_required
def profile():
    form = ProfileForm(obj=current_user)
    if request.method == "GET":
        form.username.data = current_user.username
        form.email.data = current_user.email
        form.twofa_enabled.data = current_user.twofa_enabled

    if form.validate_on_submit():
        if (
            form.username.data != current_user.username
            and User.query.filter_by(username=form.username.data).first()
        ):
            flash("Ce nom d’utilisateur est déjà utilisé.", "warning")
        else:
            if form.password.data and (not form.confirm_password.data or form.password.data != form.confirm_password.data):
                flash("Merci de confirmer le nouveau mot de passe.", "danger")
                return render_template("dashboard/profile.html", form=form)
            if form.twofa_enabled.data and not form.email.data and not current_user.email:
                flash("Un email valide est requis pour activer la 2FA.", "danger")
                return render_template("dashboard/profile.html", form=form)
            twofa_before = current_user.twofa_enabled
            original_state = {
                "username": current_user.username,
                "email": current_user.email,
                "twofa_enabled": current_user.twofa_enabled,
            }
            if form.remove_avatar.data:
                delete_avatar(current_user.avatar_filename)
                current_user.avatar_filename = None
            elif form.avatar.data:
                delete_avatar(current_user.avatar_filename)
                current_user.avatar_filename = save_avatar(form.avatar.data)
            current_user.username = form.username.data
            current_user.email = form.email.data
            if form.twofa_enabled.data:
                current_user.twofa_enabled = True
            else:
                current_user.twofa_enabled = False
                current_user.twofa_code_hash = None
                current_user.twofa_code_sent_at = None
                current_user.twofa_trusted_token_hash = None
                current_user.twofa_trusted_created_at = None
            if form.password.data:
                current_user.set_password(form.password.data)
            db.session.add(current_user)
            db.session.add(
                JournalEntry(
                    level="info",
                    message=f"Profil mis à jour pour {current_user.username}",
                    details={
                        "user_id": current_user.id,
                        "modified_by": current_user.username,
                        "changes": build_changes(
                            original_state,
                            {
                                "username": current_user.username,
                                "email": current_user.email,
                                "twofa_enabled": current_user.twofa_enabled,
                            },
                            list(original_state.keys()),
                        ),
                    },
                )
            )
            if twofa_before != current_user.twofa_enabled:
                status = "activée" if current_user.twofa_enabled else "désactivée"
                db.session.add(
                    JournalEntry(
                        level="info",
                        message=f"2FA {status} pour {current_user.username}",
                        details={"user_id": current_user.id},
                    )
                )
                create_notification(
                    user=current_user,
                    title="Double authentification",
                    message=f"La 2FA a été {status} sur votre compte.",
                    level="success" if current_user.twofa_enabled else "info",
                    persistent=True,
                    action_endpoint="main.profile",
                )
            db.session.commit()
            flash("Profil mis à jour.", "success")
            return redirect(url_for("main.profile"))

    return render_template("dashboard/profile.html", form=form)


@main_bp.route("/notifications/read", methods=["POST"])
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


@main_bp.route("/notifications/clear", methods=["POST"])
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


@main_bp.route("/manifest.json")
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


@main_bp.route("/service-worker.js")
def service_worker():
    response = current_app.response_class(
        current_app.open_resource("static/js/service-worker.js").read(),
        mimetype="application/javascript",
    )
    response.cache_control.max_age = 0
    return response


@main_bp.errorhandler(404)
def not_found(error):  # type: ignore[override]
    return render_template("errors/404.html"), 404


@main_bp.errorhandler(500)
def internal_error(error):  # type: ignore[override]
    db.session.rollback()
    return render_template("errors/500.html"), 500
