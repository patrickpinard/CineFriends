"""Routes PWA, health check, API serveur et gestionnaires d'erreurs."""

from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

from flask import current_app, jsonify, render_template, send_from_directory, url_for
from flask_login import login_required

from .. import db
from . import main_bp


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Icônes PWA
# ---------------------------------------------------------------------------

@main_bp.route("/icon/<int:size>.png", endpoint="generate_icon")
def generate_icon(size: int):
    try:
        from PIL import Image

        logo_path = Path(current_app.static_folder) / "img" / "logo.png"
        if not logo_path.exists():
            return send_from_directory(current_app.static_folder, "img/logo.png"), 404

        logo = Image.open(logo_path)
        icon = Image.new("RGB", (size, size), color="white")
        logo_size = min(size - 40, logo.width, logo.height)
        logo_resized = logo.resize((logo_size, logo_size), Image.Resampling.LANCZOS)
        x = y = (size - logo_size) // 2

        if logo.mode == "RGBA":
            icon.paste(logo_resized, (x, y), logo_resized)
        else:
            icon.paste(logo_resized, (x, y))

        output = BytesIO()
        icon.save(output, format="PNG")
        output.seek(0)

        return current_app.response_class(
            output.read(),
            mimetype="image/png",
            headers={"Cache-Control": "public, max-age=31536000"},
        )
    except ImportError:
        return send_from_directory(current_app.static_folder, "img/logo.png")
    except Exception as exc:
        current_app.logger.error(f"Erreur génération icône {size}x{size}: {exc}")
        return send_from_directory(current_app.static_folder, "img/logo.png")


# ---------------------------------------------------------------------------
# Manifest et assets PWA
# ---------------------------------------------------------------------------

@main_bp.route("/manifest.json")
def manifest():
    sizes = [180, 192, 256, 512]
    icons = [
        {
            "src": url_for("main.generate_icon", size=s, _external=True),
            "sizes": f"{s}x{s}",
            "type": "image/png",
            "purpose": "any",
        }
        for s in sizes
    ]
    return jsonify({
        "name": "TemplateApp",
        "short_name": "TemplateApp",
        "start_url": "/",
        "display": "standalone",
        "background_color": "#ffffff",
        "theme_color": "#0f172a",
        "lang": "fr",
        "scope": "/",
        "orientation": "any",
        "icons": icons,
    })


@main_bp.route("/offline.html")
def offline():
    return render_template("offline.html")


@main_bp.route("/service-worker.js")
def service_worker():
    response = current_app.response_class(
        current_app.open_resource("static/js/service-worker.js").read(),
        mimetype="application/javascript",
    )
    response.cache_control.max_age = 0
    response.headers["Service-Worker-Allowed"] = "/"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


# ---------------------------------------------------------------------------
# Health check & API
# ---------------------------------------------------------------------------

@main_bp.route("/health")
def health():
    from sqlalchemy import text

    db_status = "error"
    try:
        db.session.execute(text("SELECT 1"))
        db.session.commit()
        db_status = "ok"
    except Exception:
        db.session.rollback()

    status = "ok" if db_status == "ok" else "degraded"
    return jsonify({
        "status": status,
        "database": db_status,
        "timestamp": _utcnow().isoformat(),
    }), (200 if db_status == "ok" else 503)


@main_bp.route("/api/server-time")
@login_required
def server_time():
    now_local = datetime.now()
    now_utc = _utcnow()
    return jsonify({
        "timestamp": now_local.isoformat(),
        "utc": now_utc.isoformat(),
        "local": now_local.strftime("%H:%M:%S"),
        "date": now_local.strftime("%d/%m/%Y"),
        "timezone_offset": (now_local - now_utc.replace(tzinfo=None)).total_seconds() / 3600,
    })


# ---------------------------------------------------------------------------
# Gestionnaires d'erreurs
# ---------------------------------------------------------------------------

@main_bp.errorhandler(404)
def not_found(error):  # type: ignore[override]
    return render_template("errors/404.html"), 404


@main_bp.errorhandler(500)
def internal_error(error):  # type: ignore[override]
    db.session.rollback()
    return render_template("errors/500.html"), 500
