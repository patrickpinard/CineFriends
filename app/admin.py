from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from . import db
from .forms import UserForm
from .mailer import send_email
from .models import User
from .services import create_notification, notify_admins
from .utils import build_changes, delete_avatar, save_avatar


admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


def _require_admin():
    if current_user.role != "admin":
        flash("Accès réservé à l’administrateur.", "danger")
        return False
    return True


@admin_bp.before_request
def before_request():
    if not current_user.is_authenticated:
        return
    if not _require_admin():
        return redirect(url_for("main.dashboard"))


@admin_bp.route("/utilisateurs")
@login_required
def users():
    search = request.args.get("q", "").strip()
    role = request.args.get("role", "")
    status = request.args.get("status", "")
    sort = request.args.get("sort", "recent")

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

    if sort == "name":
        query = query.order_by(User.username.asc())
    else:
        query = query.order_by(User.created_at.desc())

    users_list = query.all()

    return render_template(
        "dashboard/users.html",
        users=users_list,
        filters={"q": search, "role": role, "status": status, "sort": sort},
    )


@admin_bp.route("/utilisateurs/nouveau", methods=["GET", "POST"])
@login_required
def create_user():
    form = UserForm()
    if form.validate_on_submit():
        if User.query.filter_by(username=form.username.data).first():
            flash("Nom d'utilisateur déjà utilisé.", "warning")
        elif (
            form.email.data
            and form.email.data.strip()
            and User.query.filter_by(email=form.email.data.strip()).first()
        ):
            flash(f"L'adresse email « {form.email.data.strip()} » est déjà utilisée par un autre compte. Veuillez utiliser une autre adresse email.", "warning")
            return render_template("dashboard/user_form.html", form=form, is_edit=False, user=None)
        else:
            if form.twofa_enabled.data and not form.email.data:
                flash("Un email est requis pour activer la 2FA.", "danger")
                return render_template("dashboard/user_form.html", form=form, is_edit=False, user=None)
            user = User(
                title=form.title.data.strip() if form.title.data else None,
                first_name=form.first_name.data.strip() if form.first_name.data else None,
                last_name=form.last_name.data.strip() if form.last_name.data else None,
                username=form.username.data,
                email=form.email.data.strip() if form.email.data else None,
                role=form.role.data,
                active=form.active.data,
            )
            if form.avatar.data:
                user.avatar_filename = save_avatar(form.avatar.data)
            user.street = form.street.data.strip() if form.street.data else None
            user.postal_code = form.postal_code.data.strip() if form.postal_code.data else None
            user.city = form.city.data.strip() if form.city.data else None
            user.country = form.country.data.strip() if form.country.data else None
            user.phone = form.phone.data.strip() if form.phone.data else None
            user.twofa_enabled = form.twofa_enabled.data
            if not user.twofa_enabled:
                user.twofa_code_hash = None
                user.twofa_code_sent_at = None
                user.twofa_trusted_token_hash = None
                user.twofa_trusted_created_at = None
            if not form.password.data:
                flash("Mot de passe requis.", "danger")
                return render_template("dashboard/user_form.html", form=form, is_edit=False, user=None)
            if not form.confirm_password.data or form.password.data != form.confirm_password.data:
                flash("Merci de confirmer le mot de passe.", "danger")
                return render_template("dashboard/user_form.html", form=form, is_edit=False)
            user.set_password(form.password.data)
            db.session.add(user)
            db.session.commit()
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
                message=f"{current_user.username} a créé le compte « {user.username} ».",
                level="info",
                action_endpoint="admin.users",
                persistent=True,
            )
            flash("Utilisateur créé.", "success")
            return redirect(url_for("admin.users"))
    return render_template("dashboard/user_form.html", form=form, is_edit=False, user=None)


@admin_bp.route("/utilisateurs/<int:user_id>/modifier", methods=["GET", "POST"])
@login_required
def edit_user(user_id: int):
    user = User.query.get_or_404(user_id)
    form = UserForm(obj=user)
    if form.validate_on_submit():
        if user.username != form.username.data and User.query.filter_by(username=form.username.data).first():
            flash(f"Le nom d'utilisateur « {form.username.data} » est déjà utilisé par un autre compte. Veuillez en choisir un autre.", "warning")
            return render_template("dashboard/user_form.html", form=form, is_edit=True, user=user)
        elif (
            form.email.data
            and form.email.data.strip()
            and form.email.data.strip() != (user.email or "").strip()
            and User.query.filter_by(email=form.email.data.strip()).first()
        ):
            flash(f"L'adresse email « {form.email.data.strip()} » est déjà utilisée par un autre compte. Veuillez utiliser une autre adresse email.", "warning")
            return render_template("dashboard/user_form.html", form=form, is_edit=True, user=user)
        else:
            if form.twofa_enabled.data and not form.email.data:
                flash("Un email est requis pour activer la 2FA.", "danger")
                return render_template("dashboard/user_form.html", form=form, is_edit=True, user=user)
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
            if form.remove_avatar.data:
                delete_avatar(user.avatar_filename)
                user.avatar_filename = None
            elif form.avatar.data:
                delete_avatar(user.avatar_filename)
                user.avatar_filename = save_avatar(form.avatar.data)
            user.title = form.title.data.strip() if form.title.data else None
            user.first_name = form.first_name.data.strip() if form.first_name.data else None
            user.last_name = form.last_name.data.strip() if form.last_name.data else None
            user.username = form.username.data
            user.email = form.email.data.strip() if form.email.data else None
            user.role = form.role.data
            user.street = form.street.data.strip() if form.street.data else None
            user.postal_code = form.postal_code.data.strip() if form.postal_code.data else None
            user.city = form.city.data.strip() if form.city.data else None
            user.country = form.country.data.strip() if form.country.data else None
            user.phone = form.phone.data.strip() if form.phone.data else None
            if user.username == "admin":
                user.active = True
            else:
                user.active = form.active.data
            if form.twofa_enabled.data:
                user.twofa_enabled = True
            else:
                user.twofa_enabled = False
                user.twofa_code_hash = None
                user.twofa_code_sent_at = None
                user.twofa_trusted_token_hash = None
                user.twofa_trusted_created_at = None
            if form.password.data:
                if not form.confirm_password.data or form.password.data != form.confirm_password.data:
                    flash("Merci de confirmer le nouveau mot de passe.", "danger")
                    return render_template("dashboard/user_form.html", form=form, is_edit=True, user=user)
                user.set_password(form.password.data)
            db.session.add(user)
            updated_state = {
                "username": user.username,
                "email": user.email,
                "role": user.role,
                "active": user.active,
                "twofa_enabled": user.twofa_enabled,
                "avatar_filename": user.avatar_filename,
            }
            if twofa_before != user.twofa_enabled:
                status = "activée" if user.twofa_enabled else "désactivée"
                if user.email:
                    create_notification(
                        user=user,
                        title="Double authentification",
                        message=f"La 2FA a été {status} par un administrateur.",
                        level="success" if user.twofa_enabled else "info",
                        persistent=True,
                        action_endpoint="main.profile",
                    )
            db.session.commit()
            if not was_active and user.active and user.email:
                text_body = render_template("email/account_approved.txt", user=user)
                html_body = render_template("email/account_approved.html", user=user)
                send_email(
                    subject="TemplateApp — Votre accès est activé",
                    recipients=user.email,
                    body=text_body,
                    html_body=html_body,
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
                    title="Compte utilisateur activé",
                    message=f"{current_user.username} a activé le compte « {user.username} ».",
                    level="success",
                    action_endpoint="admin.users",
                    persistent=True,
                )
                flash("Utilisateur activé et notification envoyée.", "success")
            elif was_active and not user.active and user.email:
                text_body = render_template("email/account_deactivated.txt", user=user)
                html_body = render_template("email/account_deactivated.html", user=user)
                send_email(
                    subject="TemplateApp — Compte désactivé",
                    recipients=user.email,
                    body=text_body,
                    html_body=html_body,
                )
                create_notification(
                    title="Compte désactivé",
                    message="Votre accès à TemplateApp a été suspendu par un administrateur.",
                    user=user,
                    level="warning",
                    persistent=True,
                )
                notify_admins(
                    title="Compte utilisateur désactivé",
                    message=f"{current_user.username} a désactivé le compte « {user.username} ».",
                    level="warning",
                    action_endpoint="admin.users",
                    persistent=True,
                )
                flash("Utilisateur désactivé et notification envoyée.", "info")
            else:
                flash("Utilisateur mis à jour.", "success")
                notify_admins(
                    title="Profil utilisateur mis à jour",
                    message=f"{current_user.username} a modifié les informations de « {user.username} ».",
                    level="info",
                    action_endpoint="admin.users",
                    persistent=False,
                )
            return redirect(url_for("admin.users"))
    return render_template("dashboard/user_form.html", form=form, is_edit=True, user=user)


@admin_bp.route("/utilisateurs/<int:user_id>/supprimer", methods=["POST"])
@login_required
def delete_user(user_id: int):
    user = User.query.get_or_404(user_id)
    if user.username == "admin":
        flash("Impossible de supprimer le compte administrateur par défaut.", "danger")
        return redirect(url_for("admin.users"))
    delete_avatar(user.avatar_filename)
    db.session.delete(user)
    db.session.commit()
    notify_admins(
        title="Utilisateur supprimé",
        message=f"{current_user.username} a supprimé le compte « {user.username} ».",
        level="warning",
        action_endpoint="admin.users",
        persistent=True,
    )
    flash("Utilisateur supprimé.", "info")
    return redirect(url_for("admin.users"))
