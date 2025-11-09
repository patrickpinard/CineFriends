from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField
from wtforms import BooleanField, PasswordField, SelectField, StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Email, EqualTo, Length, Optional, Regexp


class LoginForm(FlaskForm):
    username = StringField("Nom d’utilisateur", validators=[DataRequired(), Length(min=3, max=80)])
    password = PasswordField("Mot de passe", validators=[DataRequired(), Length(min=4, max=128)])
    remember = BooleanField("Se souvenir de moi")
    submit = SubmitField("Connexion")


class AutomationRuleForm(FlaskForm):
    name = StringField("Nom", validators=[DataRequired(), Length(max=120)])
    trigger = StringField("Déclencheur", validators=[DataRequired(), Length(max=255)])
    action = TextAreaField("Action", validators=[DataRequired(), Length(max=255)])
    submit = SubmitField("Enregistrer la règle")


class UserForm(FlaskForm):
    username = StringField("Nom d’utilisateur", validators=[DataRequired(), Length(min=3, max=80)])
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
    twofa_enabled = BooleanField("Activer la double authentification (2FA)")
    submit = SubmitField("Enregistrer")


class SettingForm(FlaskForm):
    key = StringField("Clé", validators=[DataRequired(), Length(max=120)])
    value = StringField("Valeur", validators=[Optional(), Length(max=255)])
    submit = SubmitField("Mettre à jour")


class ProfileForm(FlaskForm):
    username = StringField("Nom d’utilisateur", validators=[DataRequired(), Length(min=3, max=80)])
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
