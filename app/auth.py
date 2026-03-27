import random
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from flask import (Blueprint, current_app, flash, make_response, redirect,
                   render_template, request, session, url_for)
from flask_login import current_user, login_required, login_user, logout_user
from werkzeug.security import check_password_hash, generate_password_hash

from . import db, limiter
from .forms import LoginForm, RegisterForm, ResetPasswordRequestForm, ResetPasswordForm, TwoFactorForm
from .mailer import send_email
from .models import User
from .services import create_notification


def utcnow() -> datetime:
    """Retourne la date/heure UTC actuelle (remplace datetime.utcnow() déprécié)."""
    return datetime.now(timezone.utc)


def to_utc_aware(dt: Optional[datetime]) -> Optional[datetime]:
    """
    Rend un datetime en "UTC aware" pour éviter les erreurs lors des comparaisons.

    En pratique, certains DateTime SQLAlchemy/SQLite reviennent en datetime naïf
    (tzinfo=None). Python ne permet pas de soustraire un naïf d'un aware.
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    if dt.tzinfo != timezone.utc:
        return dt.astimezone(timezone.utc)
    return dt


auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


@auth_bp.route("/login", methods=["GET", "POST"])
@limiter.limit("20 per minute")
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
                        and utcnow() - to_utc_aware(user.twofa_trusted_created_at) <= remember_window
                        and check_password_hash(user.twofa_trusted_token_hash, trusted_token)
                    ):
                        login_user(user, remember=False)
                        user.last_login = utcnow()
                        db.session.add(user)
                        db.session.commit()
                        current_app.logger.info(f"Connexion réussie: Utilisateur « {user.username} » (2FA mémorisée) depuis {request.remote_addr}")
                        next_page = request.args.get("next")
                        response = make_response(redirect(next_page or url_for("main.dashboard")))
                        return response

                    if user.twofa_enabled:
                        if not user.email:
                            flash("La double authentification est active mais aucun email n'est défini.", "danger")
                            return redirect(url_for("auth.login"))
                        issue_ok = _issue_twofa_code(user)
                        session["twofa_user_id"] = user.id
                        session["twofa_next"] = request.args.get("next")
                        if issue_ok:
                            flash("Un code de vérification a été envoyé par e-mail.", "info")
                        else:
                            flash("Impossible d'envoyer le code 2FA. Réessayez plus tard.", "danger")
                        return redirect(url_for("auth.twofa_verify"))

                    login_user(user, remember=False)
                    user.last_login = utcnow()
                    db.session.add(user)
                    db.session.commit()
                    current_app.logger.info(f"Connexion réussie: Utilisateur « {user.username} » depuis {request.remote_addr}")
                    next_page = request.args.get("next")
                    response = make_response(redirect(next_page or url_for("main.dashboard")))
                    response.delete_cookie(remember_cookie_name)
                    return response
                else:
                    current_app.logger.warning(f"Tentative de connexion avec compte inactif « {username} » depuis {request.remote_addr}")
                    flash("Votre compte est en attente d'activation par un administrateur.", "warning")
            else:
                current_app.logger.warning(f"Tentative de connexion avec mot de passe invalide pour « {username} » depuis {request.remote_addr}")
                flash("Mot de passe incorrect.", "danger")
        else:
            current_app.logger.warning(f"Tentative de connexion avec utilisateur inexistant « {username} » depuis {request.remote_addr}")
            flash("Identifiants invalides.", "danger")
    return render_template("auth/login.html", form=form, current_year=utcnow().year)


@auth_bp.route("/logout")
@login_required
def logout():
    username = current_user.username if current_user.is_authenticated else "Inconnu"
    user_id = current_user.id if current_user.is_authenticated else None
    session.pop("twofa_user_id", None)
    session.pop("twofa_remember_login", None)
    session.pop("twofa_next", None)
    logout_user()
    current_app.logger.info(f"Déconnexion: Utilisateur « {username} » depuis {request.remote_addr}")
    response = make_response(redirect(url_for("auth.login")))
    return response


@auth_bp.route("/register", methods=["GET", "POST"])
@limiter.limit("3 per hour")
def register():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    form = RegisterForm()
    if form.validate_on_submit():
        username = (form.username.data or "").strip()
        email = (form.email.data or "").strip()

        if User.query.filter_by(username=username).first():
            form.username.errors.append("Ce nom d’utilisateur est déjà utilisé.")
        elif User.query.filter_by(email=email).first():
            form.email.errors.append("Cette adresse email est déjà associée à un compte.")
        else:
            user = User(username=username, email=email, active=False, role="user")
            user.set_password(form.password.data)
            db.session.add(user)
            db.session.commit()

            current_app.logger.info(
                f"Nouvelle inscription : « {user.username} » ({user.email}) depuis {request.remote_addr}"
            )

            email_sent = False
            if user.email:
                html_body = render_template("email/registration_pending.html", user=user, current_year=utcnow().year)
                text_body = render_template("email/registration_pending.txt", user=user)
                email_sent = send_email(
                    subject="TemplateApp \u2014 Activation en attente",
                    recipients=user.email,
                    body=text_body,
                    html_body=html_body,
                )

            create_notification(
                title="Nouvelle demande d’accès",
                message=f"« {user.username} » ({user.email}) attend la validation de son compte.",
                audience="admin",
                level="info",
                action_endpoint="admin.users",
                action_kwargs={"tab": "pending"},
                persistent=True,
            )

            return redirect(url_for("auth.registration_pending", email_sent=email_sent, user_email=user.email or ""))
    return render_template("auth/register.html", form=form, current_year=utcnow().year)


@auth_bp.route("/inscription-en-attente")
def registration_pending():
    """Page d'information après l'inscription"""
    email_sent = request.args.get("email_sent", "false").lower() == "true"
    user_email = request.args.get("user_email", "")
    
    return render_template(
        "auth/registration_pending.html",
        email_sent=email_sent,
        user_email=user_email,
        current_year=utcnow().year
    )


@auth_bp.route("/2fa", methods=["GET", "POST"])
@limiter.limit("10 per minute")
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
    now = utcnow()

    if request.method == "GET" and request.args.get("resend"):
        code_sent_at_utc = to_utc_aware(user.twofa_code_sent_at)
        if code_sent_at_utc and now - code_sent_at_utc < resend_interval:
            remaining = int((resend_interval - (now - code_sent_at_utc)).total_seconds())
            flash(f"Merci de patienter avant de renvoyer un nouveau code ({max(0, remaining)}s).", "warning")
        else:
            issue_ok = _issue_twofa_code(user)
            if issue_ok:
                flash("Un nouveau code vous a été envoyé.", "info")
            else:
                flash("Impossible d'envoyer le code 2FA. Réessayez plus tard.", "danger")
        return redirect(url_for("auth.twofa_verify"))

    form = TwoFactorForm()

    if form.validate_on_submit():
        code = form.code.data.strip()
        expected_len = int(current_app.config["TWOFA_CODE_LENGTH"])
        if len(code) != expected_len:
            current_app.logger.warning(
                f"2FA : longueur de code invalide pour « {user.username} » depuis {request.remote_addr}"
            )
            flash(f"Code invalide (attendu : {expected_len} chiffres).", "danger")
        elif not user.twofa_code_hash or not user.twofa_code_sent_at:
            flash("Aucun code actif, veuillez renvoyer un code.", "danger")
        elif utcnow() - to_utc_aware(user.twofa_code_sent_at) > ttl:
            current_app.logger.info(
                f"2FA : code expiré pour « {user.username} » depuis {request.remote_addr}"
            )
            flash("Ce code a expiré, veuillez demander un nouveau code.", "warning")
        elif not check_password_hash(user.twofa_code_hash, code):
            current_app.logger.warning(
                f"2FA : code incorrect pour « {user.username} » depuis {request.remote_addr}"
            )
            flash("Code incorrect.", "danger")
        else:
            user.twofa_code_hash = None
            user.twofa_code_sent_at = None
            user.last_login = utcnow()

            response = make_response(redirect(session.pop("twofa_next", None) or url_for("main.dashboard")))
            remember_login = False

            if form.remember_device.data:
                token = secrets.token_hex(16)
                user.twofa_trusted_token_hash = generate_password_hash(token, method='pbkdf2:sha256')
                user.twofa_trusted_created_at = utcnow()
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
            current_app.logger.info(f"Connexion réussie avec 2FA: Utilisateur « {user.username} » depuis {request.remote_addr}")
            return response

    now = utcnow()
    code_missing = not (user.twofa_code_hash and user.twofa_code_sent_at)
    code_expired = False
    code_remaining_seconds = 0
    resend_remaining_seconds = 0

    code_sent_at_utc = to_utc_aware(user.twofa_code_sent_at)
    if code_sent_at_utc:
        age = now - code_sent_at_utc
        if age > ttl:
            code_expired = True
        code_remaining_seconds = max(0, int((ttl - age).total_seconds()))
        if age < resend_interval:
            resend_remaining_seconds = max(0, int((resend_interval - age).total_seconds()))

    return render_template(
        "auth/twofa.html",
        form=form,
        user=user,
        code_expired=code_expired,
        code_missing=code_missing,
        code_remaining_seconds=code_remaining_seconds,
        resend_remaining_seconds=resend_remaining_seconds,
    )


def _issue_twofa_code(user: User) -> bool:
    code_length = current_app.config["TWOFA_CODE_LENGTH"]
    upper = 10 ** code_length
    code = f"{random.randint(0, upper - 1):0{code_length}d}"
    user.twofa_code_hash = generate_password_hash(code, method='pbkdf2:sha256')
    user.twofa_code_sent_at = utcnow()
    db.session.add(user)
    db.session.commit()

    if not user.email:
        user.twofa_code_hash = None
        user.twofa_code_sent_at = None
        db.session.add(user)
        db.session.commit()
        return False

    ttl_minutes = max(1, current_app.config["TWOFA_CODE_TTL_SECONDS"] // 60)
    html_body = render_template("email/twofa_code.html", user=user, code=code, ttl_minutes=ttl_minutes, current_year=utcnow().year)
    text_body = render_template("email/twofa_code.txt", user=user, code=code, ttl_minutes=ttl_minutes)
    success = send_email(
        subject="TemplateApp — Votre code de connexion",
        recipients=user.email,
        body=text_body,
        html_body=html_body,
    )
    if not success:
        user.twofa_code_hash = None
        user.twofa_code_sent_at = None
        db.session.add(user)
        db.session.commit()
        return False

    return True


@auth_bp.route("/reset-password", methods=["GET", "POST"])
@limiter.limit("3 per hour")
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
            user.reset_token_expires = utcnow() + timedelta(hours=1)  # Token valide 1 heure
            db.session.commit()
            
            # Logger la demande de réinitialisation
            current_app.logger.info(f"Demande de réinitialisation de mot de passe pour l'utilisateur « {user.username} » (email: {form.email.data}) depuis {request.remote_addr}")
            
            # Envoyer l'email de réinitialisation
            reset_url = url_for("auth.reset_password", token=token, _external=True)
            html_body = render_template(
                "email/reset_password.html",
                user=user,
                reset_url=reset_url,
                current_year=utcnow().year
            )
            text_body = render_template("email/reset_password.txt", user=user, reset_url=reset_url, current_year=utcnow().year)
            send_email(
                subject="TemplateApp — Réinitialisation de votre mot de passe",
                recipients=user.email,
                body=text_body,
                html_body=html_body,
            )
        else:
            # Logger les tentatives avec email inexistant (sans révéler si l'email existe)
            current_app.logger.warning(f"Tentative de réinitialisation de mot de passe avec email inexistant « {form.email.data} » depuis {request.remote_addr}")
        
        # Toujours afficher le même message pour éviter l'énumération d'emails
        flash("Si un compte existe avec cet email, un lien de réinitialisation vous a été envoyé.", "info")
        return redirect(url_for("auth.login"))
    
    return render_template("auth/reset_password_request.html", form=form, current_year=utcnow().year)


@auth_bp.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token: str):
    """Réinitialisation du mot de passe avec le token"""
    # Trouver l'utilisateur avec un token valide
    user = None
    for u in User.query.filter(User.reset_token_hash.isnot(None)).all():
        if u.reset_token_expires and to_utc_aware(u.reset_token_expires) > utcnow():
            if check_password_hash(u.reset_token_hash, token):
                user = u
                break
    
    if not user:
        # Logger les tentatives avec token invalide ou expiré
        current_app.logger.warning(f"Tentative de réinitialisation de mot de passe avec token invalide ou expiré depuis {request.remote_addr}")
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
        
        # Logger la réinitialisation réussie
        if current_user.is_authenticated and current_user.id != user.id:
            current_app.logger.info(f"Réinitialisation de mot de passe réussie pour l'utilisateur « {user.username} » par « {current_user.username} » depuis {request.remote_addr}")
        else:
            current_app.logger.info(f"Réinitialisation de mot de passe réussie pour l'utilisateur « {user.username} » depuis {request.remote_addr}")
        
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
    
    return render_template("auth/reset_password.html", form=form, token=token, current_year=utcnow().year)
