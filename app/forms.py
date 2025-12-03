from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField
from wtforms import (
    BooleanField,
    PasswordField,
    SelectField,
    StringField,
    SubmitField,
)
from wtforms.validators import DataRequired, Email, EqualTo, Length, Optional, Regexp


class LoginForm(FlaskForm):
    username = StringField("Nom d'utilisateur", validators=[DataRequired(), Length(min=3, max=80)])
    password = PasswordField("Mot de passe", validators=[DataRequired(), Length(min=4, max=128)])
    submit = SubmitField("Connexion")


class UserForm(FlaskForm):
    title = SelectField("Civilité", choices=[("", ""), ("Monsieur", "Monsieur"), ("Madame", "Madame")], validators=[Optional()])
    first_name = StringField("Prénom", validators=[Optional(), Length(max=100)])
    last_name = StringField("Nom", validators=[Optional(), Length(max=100)])
    username = StringField("Nom d'utilisateur", validators=[DataRequired(), Length(min=3, max=80)])
    email = StringField("Email", validators=[Optional(), Email(), Length(max=120)])
    role = SelectField("Rôle", choices=[("admin", "Administrateur"), ("user", "Utilisateur")])
    password = PasswordField("Mot de passe", validators=[Optional(), Length(min=4, max=128)])
    confirm_password = PasswordField(
        "Confirmer le mot de passe",
        validators=[Optional(), EqualTo("password", message="Les mots de passe doivent correspondre.")],
    )
    active = BooleanField("Actif", default=True)
    avatar = FileField("Avatar", validators=[Optional(), FileAllowed(["jpg", "jpeg", "png", "gif"], "Formats autorisés: jpg, png, gif.")])
    remove_avatar = BooleanField("Supprimer la photo")
    street = StringField("Rue", validators=[Optional(), Length(max=255)])
    postal_code = StringField("NPA", validators=[Optional(), Length(max=20)])
    city = StringField("Ville", validators=[Optional(), Length(max=255)])
    country = StringField("Pays", validators=[Optional(), Length(max=255)])
    phone = StringField("Téléphone", validators=[Optional(), Length(max=50)])
    twofa_enabled = BooleanField("Activer la double authentification (2FA)")
    submit = SubmitField("Enregistrer")


class ProfileForm(FlaskForm):
    title = SelectField("Civilité", choices=[("", ""), ("Monsieur", "Monsieur"), ("Madame", "Madame")], validators=[Optional()])
    first_name = StringField("Prénom", validators=[Optional(), Length(max=100)])
    last_name = StringField("Nom", validators=[Optional(), Length(max=100)])
    username = StringField("Nom d'utilisateur", validators=[DataRequired(), Length(min=3, max=80)])
    email = StringField("Email", validators=[Optional(), Email(), Length(max=120)])
    password = PasswordField("Nouveau mot de passe", validators=[Optional(), Length(min=4, max=128)])
    confirm_password = PasswordField(
        "Confirmer le mot de passe",
        validators=[
            Optional(),
            EqualTo("password", message="Les mots de passe doivent correspondre."),
        ],
    )
    avatar = FileField("Photo de profil", validators=[Optional(), FileAllowed(["jpg", "jpeg", "png", "gif"], "Formats autorisés: jpg, png, gif.")])
    remove_avatar = BooleanField("Supprimer la photo actuelle")
    street = StringField("Rue", validators=[Optional(), Length(max=255)])
    postal_code = StringField("NPA", validators=[Optional(), Length(max=20)])
    city = StringField("Ville", validators=[Optional(), Length(max=255)])
    country = StringField("Pays", validators=[Optional(), Length(max=255)])
    phone = StringField("Téléphone", validators=[Optional(), Length(max=50)])
    twofa_enabled = BooleanField("Activer la double authentification (2FA)")
    submit = SubmitField("Enregistrer le profil")


class RegisterForm(FlaskForm):
    username = StringField("Nom d’utilisateur", validators=[DataRequired(), Length(min=3, max=80)])
    email = StringField("Email", validators=[DataRequired(), Email(), Length(max=120)])
    password = PasswordField("Mot de passe", validators=[DataRequired(), Length(min=4, max=128)])
    confirm_password = PasswordField(
        "Confirmer le mot de passe",
        validators=[DataRequired(), EqualTo("password", message="Les mots de passe doivent correspondre.")],
    )
    submit = SubmitField("Créer mon compte")


class TwoFactorForm(FlaskForm):
    code = StringField(
        "Code de vérification",
        validators=[DataRequired(), Length(min=6, max=6), Regexp(r"^\d+$", message="Code invalide.")],
    )
    remember_device = BooleanField("Mémoriser cet appareil")
    submit = SubmitField("Valider")


class ResetPasswordRequestForm(FlaskForm):
    email = StringField("Email", validators=[DataRequired(), Email(), Length(max=120)])
    submit = SubmitField("Demander la réinitialisation")


class ResetPasswordForm(FlaskForm):
    password = PasswordField("Nouveau mot de passe", validators=[DataRequired(), Length(min=4, max=128)])
    confirm_password = PasswordField(
        "Confirmer le mot de passe",
        validators=[DataRequired(), EqualTo("password", message="Les mots de passe doivent correspondre.")],
    )
    submit = SubmitField("Réinitialiser le mot de passe")
