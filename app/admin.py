import csv
import io
import json
import secrets
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from flask import Blueprint, current_app, flash, make_response, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from werkzeug.security import generate_password_hash

from . import db, limiter
from .forms import BroadcastNotificationForm, ProfileForm
from .mailer import send_email
from .models import User
from .services import create_notification, notify_admins
from .utils import delete_avatar, populate_form_from_user, save_avatar


admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


# ---------------------------------------------------------------------------
# Helpers privés
# ---------------------------------------------------------------------------

def _handle_avatar(form, user) -> None:
    """Gère l'upload ou la suppression de l'avatar d'un utilisateur."""
    if form.remove_avatar.data:
        delete_avatar(user.avatar_filename)
        user.avatar_filename = None
    elif (
        form.avatar.data
        and hasattr(form.avatar.data, "filename")
        and form.avatar.data.filename
    ):
        delete_avatar(user.avatar_filename)
        user.avatar_filename = save_avatar(form.avatar.data)



def _apply_user_fields(user, form) -> None:
    """Applique tous les champs du formulaire sur l'objet utilisateur."""
    user.title = (form.title.data or "").strip() or None
    user.first_name = (form.first_name.data or "").strip() or None
    user.last_name = (form.last_name.data or "").strip() or None
    user.email = (form.email.data or "").strip() or None
    user.date_of_birth = form.date_of_birth.data
    user.bio = (form.bio.data or "").strip() or None
    user.company = (form.company.data or "").strip() or None
    user.job_title = (form.job_title.data or "").strip() or None
    user.website = (form.website.data or "").strip() or None
    user.linkedin = (form.linkedin.data or "").strip() or None
    user.street = (form.street.data or "").strip() or None
    user.postal_code = (form.postal_code.data or "").strip() or None
    user.city = (form.city.data or "").strip() or None
    user.country = (form.country.data or "").strip() or None
    user.phone = (form.phone.data or "").strip() or None
    user.phone_mobile = (form.phone_mobile.data or "").strip() or None
    user.email_professional = (form.email_professional.data or "").strip() or None
    user.street_professional = (form.street_professional.data or "").strip() or None
    user.postal_code_professional = (form.postal_code_professional.data or "").strip() or None
    user.city_professional = (form.city_professional.data or "").strip() or None
    user.country_professional = (form.country_professional.data or "").strip() or None
    user.phone_professional = (form.phone_professional.data or "").strip() or None


def _build_audit_changes(original: dict, updated: dict, form) -> list:
    """Construit la liste des changements entre deux états pour le journal d'audit."""
    changes = []
    if original["username"] != updated["username"]:
        changes.append(
            f"nom d'utilisateur: \u00ab {original['username']} \u00bb \u2192 \u00ab {updated['username']} \u00bb"
        )
    if original["email"] != updated["email"]:
        changes.append(
            f"email: \u00ab {original['email'] or 'aucun'} \u00bb \u2192 \u00ab {updated['email'] or 'aucun'} \u00bb"
        )
    if original["role"] != updated["role"]:
        changes.append(f"r\u00f4le: {original['role']} \u2192 {updated['role']}")
    if original["active"] != updated["active"]:
        old = "Actif" if original["active"] else "Inactif"
        new = "Actif" if updated["active"] else "Inactif"
        changes.append(f"statut: {old} \u2192 {new}")
    if original["twofa_enabled"] != updated["twofa_enabled"]:
        old = "Activ\u00e9e" if original["twofa_enabled"] else "D\u00e9sactiv\u00e9e"
        new = "Activ\u00e9e" if updated["twofa_enabled"] else "D\u00e9sactiv\u00e9e"
        changes.append(f"2FA: {old} \u2192 {new}")
    if form.password.data:
        changes.append("mot de passe modifi\u00e9")
    if original["avatar_filename"] != updated["avatar_filename"]:
        changes.append("photo de profil modifi\u00e9e")
    return changes


# ---------------------------------------------------------------------------
# Guard admin
# ---------------------------------------------------------------------------

def _require_admin():
    if current_user.role != "admin":
        flash("Accès réservé à l'administrateur.", "danger")
        return False
    return True


@admin_bp.before_request
def before_request():
    if not current_user.is_authenticated:
        return
    if not _require_admin():
        return redirect(url_for("main.dashboard"))


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@admin_bp.route("/utilisateurs")
@login_required
def users():
    from collections import defaultdict

    tab = request.args.get("tab", "all")
    pending_count = User.query.filter_by(active=False).count()

    # ── Tab "En attente" ─────────────────────────────────────────────────────
    if tab == "pending":
        search = request.args.get("q", "").strip()
        query = User.query.filter_by(active=False)
        if search:
            like = f"%{search}%"
            query = query.filter(db.or_(User.username.ilike(like), User.email.ilike(like)))
        pending_users = query.order_by(User.created_at.desc()).all()

        by_day: dict = defaultdict(list)
        for u in pending_users:
            day = u.created_at.date() if u.created_at else datetime.utcnow().date()
            by_day[day].append(u)
        sorted_days = sorted(by_day.keys(), reverse=True)
        groups = [{"date": d, "users": by_day[d]} for d in sorted_days]
        today = datetime.utcnow().date()
        yesterday = datetime.utcnow().date().__class__.fromordinal(today.toordinal() - 1)

        return render_template(
            "dashboard/users.html",
            tab=tab,
            pending_count=pending_count,
            groups=groups,
            pending_total=len(pending_users),
            search=search,
            today=today,
            yesterday=yesterday,
            users=[],
            pagination=None,
            filters={},
        )

    # ── Tab "Tous les utilisateurs" (défaut) ─────────────────────────────────
    db.session.expire_all()
    search = request.args.get("q", "").strip()
    role = request.args.get("role", "")
    status = request.args.get("status", "")
    sort = request.args.get("sort", "recent")
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 10, type=int)

    query = User.query
    if search:
        like = f"%{search}%"
        query = query.filter(db.or_(User.username.ilike(like), User.email.ilike(like)))
    if role in {"admin", "user"}:
        query = query.filter_by(role=role)
    if status == "active":
        query = query.filter_by(active=True)
    elif status == "inactive":
        query = query.filter_by(active=False)

    sort_order = request.args.get("order", "desc" if sort == "recent" else "asc")
    if sort == "name":
        query = query.order_by(User.username.desc() if sort_order == "desc" else User.username.asc())
    elif sort == "email":
        query = query.order_by(User.email.desc() if sort_order == "desc" else User.email.asc())
    elif sort == "role":
        query = query.order_by(User.role.desc() if sort_order == "desc" else User.role.asc())
    elif sort == "status":
        query = query.order_by(User.active.desc() if sort_order == "desc" else User.active.asc())
    elif sort == "last_login":
        query = query.order_by(
            User.last_login.desc().nullslast() if sort_order == "desc"
            else User.last_login.asc().nullslast()
        )
    else:
        query = query.order_by(User.created_at.desc())

    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    return render_template(
        "dashboard/users.html",
        tab=tab,
        pending_count=pending_count,
        users=pagination.items,
        pagination=pagination,
        filters={"q": search, "role": role, "status": status, "sort": sort, "order": sort_order},
        groups=[],
        pending_total=0,
        search="",
        today=None,
        yesterday=None,
    )


@admin_bp.route("/utilisateurs/export")
@login_required
def export_users():
    """Export de la liste des utilisateurs au format CSV ou JSON (admin uniquement)."""
    fmt = request.args.get("format", "csv").lower()
    search = request.args.get("q", "").strip()
    role = request.args.get("role", "")
    status = request.args.get("status", "")

    query = User.query
    if search:
        like = f"%{search}%"
        query = query.filter(db.or_(User.username.ilike(like), User.email.ilike(like)))
    if role in {"admin", "user"}:
        query = query.filter_by(role=role)
    if status == "active":
        query = query.filter_by(active=True)
    elif status == "inactive":
        query = query.filter_by(active=False)
    all_users = query.order_by(User.username.asc()).all()

    def _fmt_dt(dt):
        return dt.strftime("%Y-%m-%d %H:%M:%S") if dt else ""

    rows = [
        {
            "username":      u.username or "",
            "email":         u.email or "",
            "role":          u.role or "",
            "actif":         "oui" if u.active else "non",
            "prenom":        u.first_name or "",
            "nom":           u.last_name or "",
            "telephone":     u.phone or "",
            "entreprise":    u.company or "",
            "poste":         u.job_title or "",
            "2fa":           "oui" if u.twofa_enabled else "non",
            "cree_le":       _fmt_dt(u.created_at),
            "derniere_connexion": _fmt_dt(u.last_login),
        }
        for u in all_users
    ]

    now_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    current_app.logger.info(
        f"Export {fmt.upper()} utilisateurs par {current_user.username} ({len(rows)} entrées)"
    )

    if fmt == "json":
        body = json.dumps(rows, ensure_ascii=False, indent=2)
        resp = make_response(body)
        resp.headers["Content-Type"] = "application/json; charset=utf-8"
        resp.headers["Content-Disposition"] = f"attachment; filename=utilisateurs_{now_str}.json"
        return resp

    output = io.StringIO()
    fieldnames = ["username", "email", "role", "actif", "prenom", "nom",
                  "telephone", "entreprise", "poste", "2fa", "cree_le", "derniere_connexion"]
    writer = csv.DictWriter(output, fieldnames=fieldnames, quoting=csv.QUOTE_ALL)
    writer.writeheader()
    writer.writerows(rows)
    resp = make_response(output.getvalue())
    resp.headers["Content-Type"] = "text/csv; charset=utf-8"
    resp.headers["Content-Disposition"] = f"attachment; filename=utilisateurs_{now_str}.csv"
    return resp


@admin_bp.route("/utilisateurs/import", methods=["POST"])
@login_required
def import_users():
    """Import d'utilisateurs depuis un fichier CSV ou JSON (admin uniquement)."""
    uploaded = request.files.get("file")
    if not uploaded or not uploaded.filename:
        flash("Aucun fichier sélectionné.", "danger")
        return redirect(url_for("admin.users"))

    filename = uploaded.filename.lower()
    content  = uploaded.read().decode("utf-8-sig")  # utf-8-sig gère le BOM Excel

    # ── Parsing ──────────────────────────────────────────────────────────────
    rows = []
    try:
        if filename.endswith(".json"):
            rows = json.loads(content)
            if not isinstance(rows, list):
                raise ValueError("Le fichier JSON doit être un tableau d'objets.")
        elif filename.endswith(".csv"):
            reader = csv.DictReader(io.StringIO(content))
            rows = list(reader)
        else:
            flash("Format non supporté. Utilisez un fichier .csv ou .json.", "danger")
            return redirect(url_for("admin.users"))
    except Exception as exc:
        flash(f"Erreur de lecture du fichier : {exc}", "danger")
        return redirect(url_for("admin.users"))

    # ── Traitement ligne par ligne ────────────────────────────────────────────
    created = skipped = errors = 0
    error_details = []

    for i, row in enumerate(rows, start=1):
        username = (row.get("username") or "").strip()
        if not username:
            errors += 1
            error_details.append(f"Ligne {i} : username manquant.")
            continue

        if User.query.filter_by(username=username).first():
            skipped += 1
            continue

        email = (row.get("email") or "").strip() or None
        if email and User.query.filter_by(email=email).first():
            errors += 1
            error_details.append(f"Ligne {i} ({username}) : email « {email} » déjà utilisé.")
            continue

        role = row.get("role", "user").strip().lower()
        if role not in {"admin", "user"}:
            role = "user"

        actif_raw = row.get("actif", "non").strip().lower()
        active = actif_raw in ("oui", "true", "1", "yes")

        tmp_password = secrets.token_urlsafe(16)
        u = User(username=username)
        u.set_password(tmp_password)
        u.email      = email
        u.role       = role
        u.active     = active
        u.first_name = (row.get("prenom") or "").strip() or None
        u.last_name  = (row.get("nom") or "").strip() or None
        u.phone      = (row.get("telephone") or "").strip() or None
        u.company    = (row.get("entreprise") or "").strip() or None
        u.job_title  = (row.get("poste") or "").strip() or None

        db.session.add(u)
        created += 1

    db.session.commit()

    # ── Flash récapitulatif ───────────────────────────────────────────────────
    parts = []
    if created:  parts.append(f"{created} créé{'s' if created > 1 else ''}")
    if skipped:  parts.append(f"{skipped} ignoré{'s' if skipped > 1 else ''} (déjà existants)")
    if errors:   parts.append(f"{errors} erreur{'s' if errors > 1 else ''}")
    flash(f"Import terminé — {', '.join(parts)}.", "success" if not errors else "warning")

    for detail in error_details[:5]:  # Limiter l'affichage à 5 détails
        flash(detail, "warning")

    current_app.logger.info(
        f"Import utilisateurs par {current_user.username} — "
        f"{created} créés, {skipped} ignorés, {errors} erreurs (fichier : {uploaded.filename})"
    )
    return redirect(url_for("admin.users"))


@admin_bp.route("/utilisateurs/nouveau", methods=["GET", "POST"])
@limiter.limit("100 per hour")
@login_required
def create_user():
    form = ProfileForm()
    if form.validate_on_submit():
        if User.query.filter_by(username=form.username.data).first():
            flash("Nom d'utilisateur déjà utilisé.", "warning")
            return render_template("dashboard/profile.html", form=form, user=None)

        new_email = (form.email.data or "").strip()
        if new_email and User.query.filter_by(email=new_email).first():
            flash(
                f"L'adresse email \u00ab\u00a0{new_email}\u00a0\u00bb est déjà utilisée. "
                "Veuillez utiliser une autre adresse email.",
                "warning",
            )
            return render_template("dashboard/profile.html", form=form, user=None)

        if form.twofa_enabled.data and not new_email:
            flash("Un email est requis pour activer la 2FA.", "danger")
            return render_template("dashboard/profile.html", form=form, user=None)

        password = (form.password.data or "").strip()
        confirm = (form.confirm_password.data or "").strip()
        has_errors = False
        if not password:
            form.password.errors.append("Le mot de passe est obligatoire pour créer un utilisateur.")
            has_errors = True
        if not confirm:
            form.confirm_password.errors.append("La confirmation du mot de passe est obligatoire.")
            has_errors = True
        if password and confirm and password != confirm:
            form.confirm_password.errors.append("Les mots de passe ne correspondent pas.")
            has_errors = True
        if has_errors:
            flash("Veuillez corriger les erreurs dans le formulaire.", "danger")
            return render_template("dashboard/profile.html", form=form, user=None)

        active_value = (
            form.active.data
            if hasattr(form, "active") and form.active.data is not None
            else True
        )
        user = User(username=form.username.data, role=form.role.data, active=active_value)
        _apply_user_fields(user, form)
        _handle_avatar(form, user)
        user.twofa_enabled = form.twofa_enabled.data
        if not user.twofa_enabled:
            user.twofa_code_hash = None
            user.twofa_code_sent_at = None
            user.twofa_trusted_token_hash = None
            user.twofa_trusted_created_at = None
        user.set_password(password)
        db.session.add(user)
        try:
            db.session.flush()
            db.session.commit()
            db.session.refresh(user)
            current_app.logger.info(
                f"Création d'utilisateur réussie: \u00ab {user.username} \u00bb "
                f"(ID: {user.id}, Rôle: {user.role}, "
                f"Statut: {'Actif' if user.active else 'Inactif'}) par {current_user.username}"
            )
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(
                f"Erreur lors de la création de \u00ab {form.username.data} \u00bb "
                f"par {current_user.username}: {e}"
            )
            flash("Erreur lors de la création de l'utilisateur. Veuillez réessayer.", "danger")
            return render_template("dashboard/profile.html", form=form, user=None)

        if user.email:
            create_notification(
                title="Bienvenue sur TemplateApp",
                message="Votre compte a été créé par un administrateur. Vous pouvez vous connecter avec vos identifiants.",
                user=user,
                level="info",
                action_endpoint="auth.login",
                persistent=True,
            )
        notify_admins(
            title="Nouvel utilisateur créé",
            message=f"{current_user.username} a créé le compte \u00ab {user.username} \u00bb.",
            level="info",
            action_endpoint="admin.users",
            persistent=True,
        )
        flash("Utilisateur créé.", "success")
        return redirect(url_for("admin.users"))
    else:
        if request.method == "POST":
            current_app.logger.warning(
                f"Formulaire de création invalide par {current_user.username}: {form.errors}"
            )
    return render_template("dashboard/profile.html", form=form, user=None)


@admin_bp.route("/utilisateurs/<int:user_id>/modifier", methods=["GET", "POST"])
@limiter.limit("100 per hour")
@login_required
def edit_user(user_id: int):
    user = User.query.get_or_404(user_id)
    form = ProfileForm()

    if form.validate_on_submit():
        new_username = form.username.data
        if user.username != new_username and User.query.filter_by(username=new_username).first():
            flash(
                f"Le nom d'utilisateur \u00ab {new_username} \u00bb est déjà utilisé. "
                "Veuillez en choisir un autre.",
                "warning",
            )
            return render_template("dashboard/profile.html", form=form, user=user)

        new_email = (form.email.data or "").strip()
        if (
            new_email
            and new_email != (user.email or "").strip()
            and User.query.filter_by(email=new_email).first()
        ):
            flash(
                f"L'adresse email \u00ab {new_email} \u00bb est déjà utilisée. "
                "Veuillez utiliser une autre adresse email.",
                "warning",
            )
            return render_template("dashboard/profile.html", form=form, user=user)

        if form.twofa_enabled.data and not new_email:
            flash("Un email est requis pour activer la 2FA.", "danger")
            return render_template("dashboard/profile.html", form=form, user=user)

        if form.password.data and (
            not form.confirm_password.data
            or form.password.data != form.confirm_password.data
        ):
            flash("Merci de confirmer le nouveau mot de passe.", "danger")
            return render_template("dashboard/profile.html", form=form, user=user)

        # Capturer l'état avant modification
        original_state = {
            "username": user.username,
            "email": user.email,
            "role": user.role,
            "active": user.active,
            "twofa_enabled": user.twofa_enabled,
            "avatar_filename": user.avatar_filename,
        }
        was_active = user.active
        twofa_before = user.twofa_enabled

        # Appliquer les modifications
        _handle_avatar(form, user)
        _apply_user_fields(user, form)
        user.username = new_username
        if user.username != "admin":
            user.role = form.role.data if form.role.data else user.role
        user.active = True if user.username == "admin" else (
            form.active.data if form.active.data is not None else user.active
        )
        user.twofa_enabled = bool(form.twofa_enabled.data)
        if not user.twofa_enabled:
            user.twofa_code_hash = None
            user.twofa_code_sent_at = None
            user.twofa_trusted_token_hash = None
            user.twofa_trusted_created_at = None
        if form.password.data:
            user.set_password(form.password.data)

        db.session.add(user)

        # Notification si changement 2FA
        if twofa_before != user.twofa_enabled and user.email:
            status_2fa = "activée" if user.twofa_enabled else "désactivée"
            create_notification(
                user=user,
                title="Double authentification",
                message=f"La 2FA a été {status_2fa} par un administrateur.",
                level="success" if user.twofa_enabled else "info",
                persistent=True,
                action_endpoint="main.profile",
            )

        # Journal d'audit
        updated_state = {
            "username": user.username,
            "email": user.email,
            "role": user.role,
            "active": user.active,
            "twofa_enabled": user.twofa_enabled,
            "avatar_filename": user.avatar_filename,
        }
        changes = _build_audit_changes(original_state, updated_state, form)
        if changes:
            current_app.logger.info(
                f"Modification d'utilisateur \u00ab {user.username} \u00bb "
                f"par {current_user.username}: {', '.join(changes)}"
            )
        else:
            current_app.logger.info(
                f"Modification d'utilisateur \u00ab {user.username} \u00bb "
                f"par {current_user.username} (aucun changement détecté)"
            )

        db.session.commit()

        # Notifications activation/désactivation compte
        if not was_active and user.active and user.email:
            send_email(
                subject="TemplateApp \u2014 Votre accès est activé",
                recipients=user.email,
                body=render_template("email/account_approved.txt", user=user),
                html_body=render_template("email/account_approved.html", user=user),
            )
            create_notification(
                title="Compte activé",
                message="Votre accès à TemplateApp vient d'être activé.",
                user=user, level="success",
                action_endpoint="auth.login", persistent=True,
            )
            notify_admins(
                title="Compte utilisateur activé",
                message=f"{current_user.username} a activé le compte \u00ab {user.username} \u00bb.",
                level="success", action_endpoint="admin.users", persistent=True,
            )
            flash("Utilisateur activé et notification envoyée.", "success")
        elif was_active and not user.active and user.email:
            send_email(
                subject="TemplateApp \u2014 Compte désactivé",
                recipients=user.email,
                body=render_template("email/account_deactivated.txt", user=user),
                html_body=render_template("email/account_deactivated.html", user=user),
            )
            create_notification(
                title="Compte désactivé",
                message="Votre accès à TemplateApp a été suspendu par un administrateur.",
                user=user, level="warning", persistent=True,
            )
            notify_admins(
                title="Compte utilisateur désactivé",
                message=f"{current_user.username} a désactivé le compte \u00ab {user.username} \u00bb.",
                level="warning", action_endpoint="admin.users", persistent=True,
            )
            flash("Utilisateur désactivé et notification envoyée.", "info")
        else:
            flash("Utilisateur mis à jour.", "success")
            notify_admins(
                title="Profil utilisateur mis à jour",
                message=f"{current_user.username} a modifié les informations de \u00ab {user.username} \u00bb.",
                level="info", action_endpoint="admin.users", persistent=False,
            )

        return redirect(url_for("admin.users"))

    # GET : pré-remplir le formulaire
    if request.method == "GET":
        populate_form_from_user(form, user)

    return render_template("dashboard/profile.html", form=form, user=user)


@admin_bp.route("/taches")
@login_required
def tasks():
    """Redirige vers le tab En attente de la page Utilisateurs."""
    return redirect(url_for("admin.users", tab="pending"))


@admin_bp.route("/taches/<int:user_id>/approuver", methods=["POST"])
@login_required
def approve_user(user_id: int):
    """Active un compte utilisateur en attente et envoie un email de confirmation."""
    user = User.query.get_or_404(user_id)
    user.active = True
    db.session.commit()
    current_app.logger.info(
        f"Compte \u00ab {user.username} \u00bb approuvé par {current_user.username}"
    )
    if user.email:
        send_email(
            subject="TemplateApp \u2014 Votre accès est activé",
            recipients=user.email,
            body=render_template("email/account_approved.txt", user=user),
            html_body=render_template("email/account_approved.html", user=user),
        )
        create_notification(
            title="Compte activé",
            message="Votre accès à TemplateApp vient d'être activé.",
            user=user,
            level="success",
            action_endpoint="auth.login",
            persistent=True,
        )
    notify_admins(
        title="Compte approuvé",
        message=f"{current_user.username} a approuvé le compte \u00ab {user.username} \u00bb.",
        level="success",
        action_endpoint="admin.users",
        persistent=False,
    )
    flash(f"Compte \u00ab {user.username} \u00bb activé.", "success")
    return redirect(url_for("admin.users", tab="pending"))


@admin_bp.route("/taches/<int:user_id>/rejeter", methods=["POST"])
@login_required
def reject_user(user_id: int):
    """Supprime un compte en attente (refus d'inscription)."""
    user = User.query.get_or_404(user_id)
    if user.username == "admin":
        flash("Impossible de supprimer le compte administrateur par défaut.", "danger")
        return redirect(url_for("admin.tasks"))
    username = user.username
    delete_avatar(user.avatar_filename)
    db.session.delete(user)
    db.session.commit()
    current_app.logger.info(
        f"Inscription de \u00ab {username} \u00bb rejetée par {current_user.username}"
    )
    notify_admins(
        title="Inscription rejetée",
        message=f"{current_user.username} a rejeté l'inscription de \u00ab {username} \u00bb.",
        level="warning",
        action_endpoint="admin.tasks",
        persistent=False,
    )
    flash(f"Inscription de \u00ab {username} \u00bb rejetée.", "info")
    return redirect(url_for("admin.users", tab="pending"))


@admin_bp.route("/utilisateurs/<int:user_id>/supprimer", methods=["POST"])
@login_required
def delete_user(user_id: int):
    user = User.query.get_or_404(user_id)
    if user.username == "admin":
        flash("Impossible de supprimer le compte administrateur par défaut.", "danger")
        return redirect(url_for("admin.users"))
    username_to_delete = user.username
    delete_avatar(user.avatar_filename)
    db.session.delete(user)
    db.session.commit()
    current_app.logger.info(
        f"Suppression d'utilisateur \u00ab {username_to_delete} \u00bb par {current_user.username}"
    )
    notify_admins(
        title="Utilisateur supprimé",
        message=f"{current_user.username} a supprimé le compte \u00ab {username_to_delete} \u00bb.",
        level="warning",
        action_endpoint="admin.users",
        persistent=True,
    )
    flash("Utilisateur supprimé.", "info")
    return redirect(url_for("admin.users"))


@admin_bp.route("/utilisateurs/<int:user_id>/reinitialiser-mot-de-passe", methods=["POST"])
@login_required
def reset_user_password(user_id: int):
    """Envoie un lien de réinitialisation de mot de passe à l'utilisateur."""
    user = User.query.get_or_404(user_id)
    if not user.email:
        flash(
            f"L'utilisateur « {user.username} » n'a pas d'adresse email. "
            "Impossible d'envoyer le lien.",
            "danger",
        )
        return redirect(url_for("admin.users"))

    token = secrets.token_urlsafe(32)
    user.reset_token_hash = generate_password_hash(token, method="pbkdf2:sha256")
    user.reset_token_expires = datetime.now(timezone.utc) + timedelta(hours=24)
    db.session.commit()

    reset_url = url_for("auth.reset_password", token=token, _external=True)
    send_email(
        subject="TemplateApp \u2014 Réinitialisation de votre mot de passe",
        recipients=user.email,
        body=render_template(
            "email/reset_password.txt",
            user=user,
            reset_url=reset_url,
            current_year=datetime.now().year,
        ),
        html_body=render_template(
            "email/reset_password.html",
            user=user,
            reset_url=reset_url,
            current_year=datetime.now().year,
        ),
    )

    current_app.logger.info(
        f"Réinitialisation de mot de passe envoyée pour « {user.username} » "
        f"par {current_user.username} (email: {user.email})"
    )
    create_notification(
        title="Réinitialisation de mot de passe",
        message="Un administrateur vous a envoyé un lien de réinitialisation de mot de passe.",
        user=user,
        level="info",
        persistent=True,
    )
    flash(
        f"Lien de réinitialisation envoyé à {user.email} (valable 24 h).",
        "success",
    )
    return redirect(url_for("admin.users"))


def _detect_broadcast_level(title: str) -> str:
    """Déduit le niveau d'une notification broadcast à partir de son titre."""
    t = title.lower()
    _title_map = {
        "avis de maintenance": "warning",
        "avis d'interruption de service": "error",
        "maintenance planifiée": "warning",
        "incident en cours": "error",
        "incident résolu": "info",
        "dégradation de service": "warning",
        "retour à la normale": "info",
        "nouvelle version disponible": "info",
        "mise à jour de l'application": "info",
        "information importante": "info",
        "changement de procédure": "info",
        "rappel": "info",
        "message de l'équipe": "info",
    }
    if t in _title_map:
        return _title_map[t]
    for kw in ("incident", "panne", "critique", "urgence", "interruption", "indisponible"):
        if kw in t:
            return "error"
    for kw in ("maintenance", "dégradation", "attention", "avertissement", "alerte", "lenteur"):
        if kw in t:
            return "warning"
    return "info"


@admin_bp.route("/notifications/broadcast", methods=["GET", "POST"])
@login_required
def broadcast_notification():
    """Envoie une notification globale à tous les utilisateurs."""
    form = BroadcastNotificationForm()
    if form.validate_on_submit():
        title = form.title.data.strip()
        level = _detect_broadcast_level(title)
        create_notification(
            title=title,
            message=form.message.data.strip(),
            level=level,
            audience="global",
            persistent=False,
        )
        current_app.logger.info(
            f"[BROADCAST] Notification broadcast envoyée par {current_user.username} "
            f"— titre : « {title} » "
            f"— niveau : {level} "
            f"— message : {form.message.data.strip()[:100]}"
        )
        flash("Notification envoyée à tous les utilisateurs.", "success")
        return redirect(url_for("admin.broadcast_notification"))

    return render_template("dashboard/broadcast.html", form=form)
