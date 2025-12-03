import random
import secrets
from datetime import datetime, timedelta

from flask import (Blueprint, current_app, flash, make_response, redirect,
                   render_template, request, session, url_for)
from flask_login import current_user, login_required, login_user, logout_user
from werkzeug.security import check_password_hash, generate_password_hash

from . import db
from .forms import LoginForm, RegisterForm, ResetPasswordRequestForm, ResetPasswordForm, TwoFactorForm
from .mailer import send_email
from .models import User
from .services import create_notification


auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    form = LoginForm()
    if form.validate_on_submit():
        username = form.username.data.strip() if form.username.data else ""
        password = form.password.data if form.password.data else ""
        user = User.query.filter_by(username=username).first()
        if user:
            password_valid = user.check_password(password)
            if password_valid:
                if user.active:
                    remember_cookie_name = current_app.config["TWOFA_REMEMBER_COOKIE"]
                    trusted_token = request.cookies.get(remember_cookie_name)
                    remember_window = timedelta(days=current_app.config["TWOFA_REMEMBER_DAYS"])
                    if (
                        user.twofa_enabled
                        and trusted_token
                        and user.twofa_trusted_token_hash
                        and user.twofa_trusted_created_at
                        and datetime.utcnow() - user.twofa_trusted_created_at <= remember_window
                        and check_password_hash(user.twofa_trusted_token_hash, trusted_token)
                    ):
                        login_user(user, remember=False)
                        user.last_login = datetime.utcnow()
                        db.session.add(user)
                        db.session.commit()
                        next_page = request.args.get("next")
                        response = make_response(redirect(next_page or url_for("main.dashboard")))
                        return response

                    if user.twofa_enabled:
                        if not user.email:
                            flash("La double authentification est active mais aucun email n'est défini.", "danger")
                            return redirect(url_for("auth.login"))
                        _issue_twofa_code(user)
                        session["twofa_user_id"] = user.id
                        session["twofa_next"] = request.args.get("next")
                        flash("Un code de vérification a été envoyé par e-mail.", "info")
                        return redirect(url_for("auth.twofa_verify"))

                    login_user(user, remember=False)
                    user.last_login = datetime.utcnow()
                    db.session.add(user)
                    db.session.commit()
                    next_page = request.args.get("next")
                    response = make_response(redirect(next_page or url_for("main.dashboard")))
                    response.delete_cookie(remember_cookie_name)
                    return response
                else:
                    flash("Votre compte est en attente d'activation par un administrateur.", "warning")
            else:
                flash("Identifiants invalides.", "danger")
        else:
            flash("Identifiants invalides.", "danger")
    return render_template("auth/login.html", form=form, current_year=datetime.utcnow().year)


@auth_bp.route("/logout")
@login_required
def logout():
    session.pop("twofa_user_id", None)
    session.pop("twofa_remember_login", None)
    session.pop("twofa_next", None)
    logout_user()
    response = make_response(redirect(url_for("auth.login")))
    return response


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    form = RegisterForm()
    if form.validate_on_submit():
        if User.query.filter_by(username=form.username.data).first():
            flash("Ce nom d’utilisateur est déjà pris.", "danger")
        elif User.query.filter_by(email=form.email.data).first():
            flash("Un compte existe déjà avec cet email.", "danger")
        else:
            user = User(
                username=form.username.data,
                email=form.email.data,
                active=False,
                role="user",
            )
            # Les inscriptions publiques n'ont pas de champ avatar pour le moment
            user.set_password(form.password.data)
            db.session.add(user)
            db.session.commit()

            # Envoyer un email à l'utilisateur pour confirmer la réception de sa demande
            email_sent = False
            if user.email:
                html_body = render_template("email/registration_pending.html", user=user, current_year=datetime.utcnow().year)
                text_body = render_template("email/registration_pending.txt", user=user)
                email_sent = send_email(
                    subject="TemplateApp — Activation en attente",
                    recipients=user.email,
                    body=text_body,
                    html_body=html_body,
                )
            
            # Notifier les administrateurs
            create_notification(
                title="Nouvelle demande d'accès",
                message=f"{user.username} attend validation de son compte.",
                audience="admin",
                level="info",
                action_endpoint="admin.users",
                persistent=True,
            )
            
            # Rediriger vers la page d'information
            return redirect(url_for("auth.registration_pending", email_sent=email_sent, user_email=user.email or ""))
    return render_template("auth/register.html", form=form, current_year=datetime.utcnow().year)


@auth_bp.route("/inscription-en-attente")
def registration_pending():
    """Page d'information après l'inscription"""
    email_sent = request.args.get("email_sent", "false").lower() == "true"
    user_email = request.args.get("user_email", "")
    
    return render_template(
        "auth/registration_pending.html",
        email_sent=email_sent,
        user_email=user_email,
        current_year=datetime.utcnow().year
    )


@auth_bp.route("/2fa", methods=["GET", "POST"])
def twofa_verify():
    user_id = session.get("twofa_user_id")
    if not user_id:
        return redirect(url_for("auth.login"))
    user = User.query.get_or_404(user_id)

    if not user.twofa_enabled:
        session.pop("twofa_user_id", None)
        session.pop("twofa_remember_login", None)
        session.pop("twofa_next", None)
        flash("La double authentification a été désactivée. Veuillez vous reconnecter.", "info")
        return redirect(url_for("auth.login"))

    ttl = timedelta(seconds=current_app.config["TWOFA_CODE_TTL_SECONDS"])
    resend_interval = timedelta(seconds=current_app.config["TWOFA_RESEND_INTERVAL_SECONDS"])

    if request.method == "GET" and request.args.get("resend"):
        if user.twofa_code_sent_at and datetime.utcnow() - user.twofa_code_sent_at < resend_interval:
            flash("Merci de patienter avant de renvoyer un nouveau code.", "warning")
        else:
            _issue_twofa_code(user)
            flash("Un nouveau code vous a été envoyé.", "info")
        return redirect(url_for("auth.twofa_verify"))

    form = TwoFactorForm()

    if form.validate_on_submit():
        if not user.twofa_code_hash or not user.twofa_code_sent_at:
            flash("Aucun code actif, veuillez renvoyer un code.", "danger")
        elif datetime.utcnow() - user.twofa_code_sent_at > ttl:
            flash("Ce code a expiré, veuillez demander un nouveau code.", "warning")
        elif not check_password_hash(user.twofa_code_hash, form.code.data.strip()):
            flash("Code incorrect.", "danger")
        else:
            user.twofa_code_hash = None
            user.twofa_code_sent_at = None
            user.last_login = datetime.utcnow()

            response = make_response(redirect(session.pop("twofa_next", None) or url_for("main.dashboard")))
            remember_login = False

            if form.remember_device.data:
                token = secrets.token_hex(16)
                user.twofa_trusted_token_hash = generate_password_hash(token, method='pbkdf2:sha256')
                user.twofa_trusted_created_at = datetime.utcnow()
                response.set_cookie(
                    current_app.config["TWOFA_REMEMBER_COOKIE"],
                    token,
                    max_age=current_app.config["TWOFA_REMEMBER_DAYS"] * 24 * 3600,
                    secure=current_app.config.get("SESSION_COOKIE_SECURE", False),
                    httponly=True,
                    samesite="Lax",
                )
            elif user.twofa_trusted_token_hash:
                # L’utilisateur choisit de ne plus faire confiance à l’appareil
                user.twofa_trusted_token_hash = None
                user.twofa_trusted_created_at = None
                response.delete_cookie(current_app.config["TWOFA_REMEMBER_COOKIE"])

            session.pop("twofa_user_id", None)
            db.session.add(user)
            db.session.commit()
            login_user(user, remember=remember_login)
            return response

    code_expired = False
    if user.twofa_code_sent_at and datetime.utcnow() - user.twofa_code_sent_at > ttl:
        code_expired = True

    return render_template(
        "auth/twofa.html",
        form=form,
        user=user,
        code_expired=code_expired,
        resend_interval_seconds=current_app.config["TWOFA_RESEND_INTERVAL_SECONDS"],
    )


def _issue_twofa_code(user: User) -> None:
    code_length = current_app.config["TWOFA_CODE_LENGTH"]
    upper = 10 ** code_length
    code = f"{random.randint(0, upper - 1):0{code_length}d}"
    user.twofa_code_hash = generate_password_hash(code, method='pbkdf2:sha256')
    user.twofa_code_sent_at = datetime.utcnow()
    db.session.add(user)
    db.session.commit()

    ttl_minutes = max(1, current_app.config["TWOFA_CODE_TTL_SECONDS"] // 60)
    html_body = render_template("email/twofa_code.html", user=user, code=code, ttl_minutes=ttl_minutes, current_year=datetime.utcnow().year)
    text_body = render_template("email/twofa_code.txt", user=user, code=code, ttl_minutes=ttl_minutes)
    send_email(
        subject="TemplateApp — Votre code de connexion",
        recipients=user.email,
        body=text_body,
        html_body=html_body,
    )


@auth_bp.route("/reset-password", methods=["GET", "POST"])
def reset_password_request():
    """Demande de réinitialisation de mot de passe"""
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))
    
    form = ResetPasswordRequestForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user:
            # Générer un token de réinitialisation
            token = secrets.token_urlsafe(32)
            user.reset_token_hash = generate_password_hash(token, method='pbkdf2:sha256')
            user.reset_token_expires = datetime.utcnow() + timedelta(hours=1)  # Token valide 1 heure
            db.session.commit()
            
            # Envoyer l'email de réinitialisation
            reset_url = url_for("auth.reset_password", token=token, _external=True)
            html_body = render_template(
                "email/reset_password.html",
                user=user,
                reset_url=reset_url,
                current_year=datetime.utcnow().year
            )
            text_body = render_template("email/reset_password.txt", user=user, reset_url=reset_url, current_year=datetime.utcnow().year)
            send_email(
                subject="TemplateApp — Réinitialisation de votre mot de passe",
                recipients=user.email,
                body=text_body,
                html_body=html_body,
            )
        
        # Toujours afficher le même message pour éviter l'énumération d'emails
        flash("Si un compte existe avec cet email, un lien de réinitialisation vous a été envoyé.", "info")
        return redirect(url_for("auth.login"))
    
    return render_template("auth/reset_password_request.html", form=form, current_year=datetime.utcnow().year)


@auth_bp.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token: str):
    """Réinitialisation du mot de passe avec le token"""
    # Trouver l'utilisateur avec un token valide
    user = None
    for u in User.query.filter(User.reset_token_hash.isnot(None)).all():
        if u.reset_token_expires and u.reset_token_expires > datetime.utcnow():
            if check_password_hash(u.reset_token_hash, token):
                user = u
                break
    
    if not user:
        flash("Le lien de réinitialisation est invalide ou a expiré.", "danger")
        if current_user.is_authenticated:
            return redirect(url_for("main.dashboard"))
        return redirect(url_for("auth.reset_password_request"))
    
    form = ResetPasswordForm()
    if form.validate_on_submit():
        user.set_password(form.password.data)
        user.reset_token_hash = None
        user.reset_token_expires = None
        db.session.commit()
        
        # Vérifier si l'utilisateur est déjà connecté
        if current_user.is_authenticated:
            if current_user.id == user.id:
                flash("Votre mot de passe a été réinitialisé avec succès.", "success")
            else:
                flash(f"Le mot de passe de {user.username} a été réinitialisé avec succès.", "success")
            return redirect(url_for("main.dashboard"))
        else:
            flash("Votre mot de passe a été réinitialisé avec succès. Vous pouvez maintenant vous connecter.", "success")
            return redirect(url_for("auth.login"))
    
    return render_template("auth/reset_password.html", form=form, token=token, current_year=datetime.utcnow().year)
