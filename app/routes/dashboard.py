"""Routes du tableau de bord et du journal d'activité."""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import csv
import io
import json

from flask import Response, current_app, flash, make_response, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from . import main_bp
from .. import db
from ..models import User, Notification


# ---------------------------------------------------------------------------
# Cache settings (pour usage futur)
# ---------------------------------------------------------------------------

_settings_cache: dict[str, str | None] = {}
_settings_cache_timestamp: datetime | None = None


def invalidate_settings_cache() -> None:
    """Invalide le cache des paramètres système."""
    global _settings_cache, _settings_cache_timestamp
    _settings_cache.clear()
    _settings_cache_timestamp = None


# ---------------------------------------------------------------------------
# Pages simples
# ---------------------------------------------------------------------------

@main_bp.route("/")
@login_required
def dashboard():
    stats = {}
    if current_user.role == "admin":
        stats["total"] = User.query.count()
        stats["active"] = User.query.filter_by(active=True).count()
        stats["pending"] = User.query.filter_by(active=False).count()
        stats["admins"] = User.query.filter_by(role="admin", active=True).count()
        stats["recent_logins"] = (
            User.query.filter(User.last_login.isnot(None))
            .order_by(User.last_login.desc())
            .limit(5)
            .all()
        )
        stats["broadcasts"] = (
            Notification.query.filter_by(audience="global")
            .order_by(Notification.created_at.desc())
            .limit(3)
            .all()
        )
    else:
        stats["unread"] = (
            Notification.query
            .filter(
                db.or_(
                    Notification.user_id == current_user.id,
                    Notification.audience == "global"
                )
            )
            .filter_by(read=False)
            .count()
        )
    return render_template("dashboard/index.html", stats=stats)


@main_bp.route("/graphiques")
@login_required
def charts():
    return render_template("dashboard/charts.html")


@main_bp.route("/automatisation")
@login_required
def automation():
    return render_template("dashboard/automation.html")



# ---------------------------------------------------------------------------
# Journal d'activité
# ---------------------------------------------------------------------------

# Patterns pour identifier les actions métier pertinentes
_ACTION_PATTERNS: dict[str, list[str]] = {
    "user_registered": [
        r"Nouvelle inscription",
    ],
    "user_created": [
        r"Création d'utilisateur réussie",
        r"Utilisateur créé",
        r"Commit réussi\. Utilisateur créé",
        r"a créé le compte",
        r"Nouvel utilisateur créé",
    ],
    "user_updated": [
        r"Modification d'utilisateur",
        r"Utilisateur mis à jour",
        r"Profil utilisateur mis à jour",
        r"a modifié",
    ],
    "user_deleted": [
        r"Suppression d'utilisateur",
        r"Utilisateur supprimé",
        r"a supprimé le compte",
        r"Inscription.*rejetée par",
    ],
    "login": [
        r"Connexion réussie",
        r"s'est connecté",
        r"last_login",
        r"Utilisateur ajouté à la session",
    ],
    "logout": [
        r"Déconnexion:",
        r"s'est déconnecté",
    ],
    "password_reset": [
        r"mot de passe.*réinitialisé",
        r"reset.*password",
        r"réinitialisation.*mot de passe",
        r"Réinitialisation de mot de passe",
    ],
    "account_activated": [
        r"Compte activé",
        r"accès.*activé",
        r"Compte.*approuvé par",
    ],
    "account_deactivated": [
        r"Compte désactivé",
        r"accès.*désactivé",
    ],
    "twofa_enabled": [
        r"Double authentification.*activée",
        r"2FA.*activée",
        r"twofa.*enabled",
    ],
    "twofa_disabled": [
        r"Double authentification.*désactivée",
        r"2FA.*désactivée",
        r"twofa.*disabled",
    ],
    "broadcast": [
        r"Notification broadcast",
        r"\[BROADCAST\]",
    ],
    "user_exported": [
        r"Export (CSV|JSON) utilisateurs",
        r"Export.*utilisateurs par",
        r"Export (CSV|JSON) du journal par",
        r"Export.*journal par",
    ],
    "user_imported": [
        r"Import utilisateurs par",
        r"Import.*utilisateurs.*créés",
    ],
}

_TECHNICAL_EXCLUDES = [
    "serving flask app",
    "debug mode",
    "running on",
    "restarting with stat",
    "debugger is active",
    "code 400",
    "code 500",
    "bad request",
    "get /static",
    "get /manifest.json",
    "get /api/server-time",
    "304 -",
    "200 -",
    "http/1.1",
]

_USERNAME_PATTERNS = [
    r'(?:username|utilisateur|compte)[\s:]+«\s*([a-zA-Z0-9_]+)\s*»',
    r'(?:username|utilisateur|compte)[\s:]+([a-zA-Z0-9_]+)',
    r'Utilisateur\s+«\s*([a-zA-Z0-9_]+)\s*»',
    r'pour l\'utilisateur\s+«\s*([a-zA-Z0-9_]+)\s*»',
]

_MONTH_NAMES = {
    1: "Janvier", 2: "Février", 3: "Mars", 4: "Avril",
    5: "Mai", 6: "Juin", 7: "Juillet", 8: "Août",
    9: "Septembre", 10: "Octobre", 11: "Novembre", 12: "Décembre",
}


def _is_business_log(line: str) -> bool:
    line_lower = line.lower()
    if any(exc in line_lower for exc in _TECHNICAL_EXCLUDES):
        return False
    return any(
        re.search(pattern, line, re.IGNORECASE)
        for patterns in _ACTION_PATTERNS.values()
        for pattern in patterns
    )


def _get_action_type(line: str) -> str:
    for action_type, patterns in _ACTION_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, line, re.IGNORECASE):
                return action_type
    return "other"


def _extract_username(line: str) -> str | None:
    for pattern in _USERNAME_PATTERNS:
        m = re.search(pattern, line, re.IGNORECASE)
        if m:
            return m.group(1)
    return None


def _parse_timestamp(line: str) -> datetime | None:
    m = re.search(r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', line)
    if m:
        try:
            return datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")
        except ValueError:
            pass
    m = re.search(r'\[(\d{2}/\w{3}/\d{4} \d{2}:\d{2}:\d{2})\]', line)
    if m:
        try:
            return datetime.strptime(m.group(1), "%d/%b/%Y %H:%M:%S")
        except ValueError:
            pass
    return None


def _group_logs_by_month(logs: list, page: int, per_page: int):
    logs_by_day: dict = defaultdict(list)
    for log in logs:
        if log["timestamp"]:
            day_key = log["timestamp"].date()
        else:
            m = re.search(r'(\d{4}-\d{2}-\d{2})', log["message"])
            if m:
                try:
                    day_key = datetime.strptime(m.group(1), "%Y-%m-%d").date()
                except ValueError:
                    day_key = datetime.now().date()
            else:
                day_key = datetime.now().date()
        logs_by_day[day_key].append(log)

    sorted_days = sorted(logs_by_day.keys(), reverse=True)
    start = (page - 1) * per_page
    paginated_days = sorted_days[start: start + per_page]

    result = []
    current_month = None
    current_month_data = None

    for day in paginated_days:
        month_key = (day.year, day.month)
        if current_month != month_key:
            if current_month_data:
                current_month_data["total_logs"] = sum(
                    len(d["logs"]) for d in current_month_data["days"]
                )
                result.append(current_month_data)
            current_month = month_key
            current_month_data = {
                "year": day.year,
                "month": day.month,
                "month_name": _MONTH_NAMES[day.month],
                "days": [],
                "total_logs": 0,
            }
        current_month_data["days"].append({"date": day, "logs": logs_by_day[day]})

    if current_month_data:
        current_month_data["total_logs"] = sum(
            len(d["logs"]) for d in current_month_data["days"]
        )
        result.append(current_month_data)

    return result, sorted_days, logs_by_day


_LOG_FILE = Path(__file__).parent.parent.parent / "logs" / "app.log"
_MAX_LINES_DEFAULT = 10_000


def _parse_logs(
    action_filter: str = "all",
    search_query: str = "",
    max_lines: int = _MAX_LINES_DEFAULT,
) -> tuple[list, int]:
    """Parse le fichier de log et retourne (logs filtrés, total_lignes_lues)."""
    logs: list = []
    total_lines = 0

    if not _LOG_FILE.exists():
        return logs, total_lines

    try:
        with open(_LOG_FILE, "r", encoding="utf-8", errors="ignore") as f:
            all_lines = f.readlines()

        total_lines = len(all_lines)
        # Limiter aux N dernières lignes pour les gros fichiers
        lines = all_lines[-max_lines:] if max_lines and len(all_lines) > max_lines else all_lines
        offset = total_lines - len(lines)

        for idx, raw_line in enumerate(lines):
            line = raw_line.strip()
            if not line or not _is_business_log(line):
                continue

            action_type = _get_action_type(line)
            if action_filter != "all" and action_type != action_filter:
                continue
            if search_query and search_query.lower() not in line.lower():
                continue

            log_level = "info"
            line_up = line.upper()
            if "ERROR" in line_up or "Exception" in line or "ERREUR" in line_up:
                log_level = "error"
            elif "WARNING" in line_up or "WARN" in line_up:
                log_level = "warning"
            elif "DEBUG" in line_up:
                log_level = "debug"

            ip_match = re.search(r'^(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})', line)

            logs.append({
                "line_number": offset + idx + 1,
                "level": log_level,
                "action_type": action_type,
                "message": line,
                "timestamp": _parse_timestamp(line),
                "ip_address": ip_match.group(1) if ip_match else None,
                "username": _extract_username(line),
            })

        logs.reverse()
    except Exception as e:
        current_app.logger.error(f"Erreur lors de la lecture du fichier de log: {e}")

    return logs, total_lines


@main_bp.route("/journal")
@login_required
def journal():
    if current_user.role != "admin":
        flash("Accès réservé à l'administrateur.", "danger")
        return redirect(url_for("main.dashboard"))

    action_filter = request.args.get("action", "all").lower()
    search_query = request.args.get("search", "").strip()
    year_filter = request.args.get("year", type=int)
    quarter_filter = request.args.get("quarter", type=int)
    page = max(1, int(request.args.get("page", 1)))
    per_page = int(request.args.get("per_page", 7))
    if per_page not in (7, 14, 30, 50):
        per_page = 7

    logs, total_lines = _parse_logs(action_filter, search_query)
    if not logs and _LOG_FILE.exists() and not (action_filter != "all" or search_query):
        flash("Le fichier de log n'a pas encore de données métier.", "info")
    elif not _LOG_FILE.exists():
        flash("Le fichier de log n'existe pas encore.", "info")

    # ── Périodes disponibles (année + trimestre) ──────────────────────────────
    _periods: dict = {}
    for log in logs:
        if log["timestamp"]:
            y = log["timestamp"].year
            q = (log["timestamp"].month - 1) // 3 + 1
            _periods.setdefault(y, set()).add(q)
    available_periods = {y: sorted(_periods[y]) for y in sorted(_periods.keys(), reverse=True)}

    # ── Filtre par année / trimestre ─────────────────────────────────────────
    if year_filter:
        logs = [l for l in logs if l["timestamp"] and l["timestamp"].year == year_filter]
        if quarter_filter in (1, 2, 3, 4):
            logs = [l for l in logs if (l["timestamp"].month - 1) // 3 + 1 == quarter_filter]

    logs_by_month_paginated, sorted_days, logs_by_day = _group_logs_by_month(logs, page, per_page)
    logs_by_day_paginated = [
        {"date": d, "logs": logs_by_day[d]}
        for d in sorted_days[(page - 1) * per_page: page * per_page]
    ]

    total_days = len(sorted_days)
    total_pages = (total_days + per_page - 1) // per_page if total_days > 0 else 1
    today = datetime.now().date()
    yesterday = (datetime.now() - timedelta(days=1)).date()

    return render_template(
        "dashboard/journal.html",
        logs_by_month=logs_by_month_paginated,
        logs_by_day=logs_by_day_paginated,
        total_logs=len(logs),
        total_lines=total_lines,
        total_days=total_days,
        page=page,
        per_page=per_page,
        total_pages=total_pages,
        action_filter=action_filter,
        search_query=search_query,
        year_filter=year_filter,
        quarter_filter=quarter_filter,
        available_periods=available_periods,
        today=today,
        yesterday=yesterday,
    )


@main_bp.route("/journal/export")
@login_required
def journal_export():
    """Export des logs au format CSV ou JSON (admin uniquement)."""
    if current_user.role != "admin":
        flash("Accès réservé à l'administrateur.", "danger")
        return redirect(url_for("main.dashboard"))

    fmt = request.args.get("format", "csv").lower()
    action_filter = request.args.get("action", "all").lower()
    search_query = request.args.get("search", "").strip()

    logs, _ = _parse_logs(action_filter, search_query, max_lines=0)  # 0 = tout lire

    # Sérialiser les timestamps
    export_logs = [
        {
            "line_number": log["line_number"],
            "timestamp": log["timestamp"].strftime("%Y-%m-%d %H:%M:%S") if log["timestamp"] else "",
            "level": log["level"],
            "action_type": log["action_type"],
            "username": log["username"] or "",
            "ip_address": log["ip_address"] or "",
            "message": log["message"],
        }
        for log in logs
    ]

    now_str = datetime.now().strftime("%Y%m%d_%H%M%S")

    if fmt == "json":
        body = json.dumps(export_logs, ensure_ascii=False, indent=2)
        resp = make_response(body)
        resp.headers["Content-Type"] = "application/json; charset=utf-8"
        resp.headers["Content-Disposition"] = f"attachment; filename=journal_{now_str}.json"
        current_app.logger.info(
            f"Export JSON du journal par {current_user.username} ({len(export_logs)} entrées)"
        )
        return resp

    # CSV par défaut
    output = io.StringIO()
    fieldnames = ["line_number", "timestamp", "level", "action_type", "username", "ip_address", "message"]
    writer = csv.DictWriter(output, fieldnames=fieldnames, quoting=csv.QUOTE_ALL)
    writer.writeheader()
    writer.writerows(export_logs)
    resp = make_response(output.getvalue())
    resp.headers["Content-Type"] = "text/csv; charset=utf-8"
    resp.headers["Content-Disposition"] = f"attachment; filename=journal_{now_str}.csv"
    current_app.logger.info(
        f"Export CSV du journal par {current_user.username} ({len(export_logs)} entrées)"
    )
    return resp
