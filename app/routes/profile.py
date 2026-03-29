"""Route de gestion du profil utilisateur."""

from __future__ import annotations

from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from .. import db, limiter
from ..forms import ProfileForm
from ..models import User
from ..utils import handle_avatar, populate_form_from_user
from . import main_bp


@main_bp.route("/profil", methods=["GET", "POST"])
@limiter.limit("100 per hour")
@login_required
def profile():
    form = ProfileForm()

    if request.method == "GET":
        populate_form_from_user(form, current_user)

    if form.validate_on_submit():
        # Vérification unicité username
        if (
            form.username.data != current_user.username
            and User.query.filter_by(username=form.username.data).first()
        ):
            flash(
                "Ce nom d'utilisateur est déjà utilisé par un autre compte. "
                "Veuillez en choisir un autre.",
                "warning",
            )
            return render_template("dashboard/profile.html", form=form, user=current_user)

        # Vérification unicité email
        new_email = (form.email.data or "").strip()
        if (
            new_email
            and new_email != (current_user.email or "").strip()
            and User.query.filter_by(email=new_email).first()
        ):
            flash(
                f"L'adresse email « {new_email} » est déjà utilisée par un autre compte. "
                "Veuillez utiliser une autre adresse email.",
                "warning",
            )
            return render_template("dashboard/profile.html", form=form, user=current_user)

        # Validation mot de passe
        if form.password.data and (
            not form.confirm_password.data
            or form.password.data != form.confirm_password.data
        ):
            flash("Merci de confirmer le nouveau mot de passe.", "danger")
            return render_template("dashboard/profile.html", form=form, user=current_user)

        # Validation 2FA
        if form.twofa_enabled.data and not form.email.data and not current_user.email:
            flash("Un email valide est requis pour activer la 2FA.", "danger")
            return render_template("dashboard/profile.html", form=form, user=current_user)

        twofa_before = current_user.twofa_enabled

        # Avatar
        handle_avatar(form, current_user)

        # Champs personnels
        current_user.title = (form.title.data or "").strip() or None
        current_user.first_name = (form.first_name.data or "").strip() or None
        current_user.last_name = (form.last_name.data or "").strip() or None
        current_user.email = new_email or None
        current_user.date_of_birth = form.date_of_birth.data
        current_user.bio = (form.bio.data or "").strip() or None
        current_user.company = (form.company.data or "").strip() or None
        current_user.job_title = (form.job_title.data or "").strip() or None
        current_user.website = (form.website.data or "").strip() or None
        current_user.linkedin = (form.linkedin.data or "").strip() or None
        current_user.street = (form.street.data or "").strip() or None
        current_user.postal_code = (form.postal_code.data or "").strip() or None
        current_user.city = (form.city.data or "").strip() or None
        current_user.country = (form.country.data or "").strip() or None
        current_user.phone = (form.phone.data or "").strip() or None
        current_user.phone_mobile = (form.phone_mobile.data or "").strip() or None
        current_user.email_professional = (form.email_professional.data or "").strip() or None
        current_user.street_professional = (form.street_professional.data or "").strip() or None
        current_user.postal_code_professional = (form.postal_code_professional.data or "").strip() or None
        current_user.city_professional = (form.city_professional.data or "").strip() or None
        current_user.country_professional = (form.country_professional.data or "").strip() or None
        current_user.phone_professional = (form.phone_professional.data or "").strip() or None

        # Admin uniquement : username, 2FA, rôle
        if current_user.role == "admin":
            current_user.username = form.username.data
            if form.twofa_enabled.data:
                current_user.twofa_enabled = True
            else:
                current_user.twofa_enabled = False
                current_user.twofa_code_hash = None
                current_user.twofa_code_sent_at = None
            if form.role.data and current_user.username != "admin":
                current_user.role = form.role.data
                current_user.twofa_trusted_token_hash = None
                current_user.twofa_trusted_created_at = None

        if form.password.data:
            current_user.set_password(form.password.data)

        db.session.add(current_user)
        db.session.commit()

        if twofa_before != current_user.twofa_enabled:
            status = "activée" if current_user.twofa_enabled else "désactivée"
            flash(f"Double authentification {status}.", "success")
        else:
            flash("Profil mis à jour.", "success")

        return redirect(url_for("main.profile"))

    return render_template("dashboard/profile.html", form=form, user=current_user)


