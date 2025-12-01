from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField
from wtforms import (
    BooleanField,
    DecimalField,
    HiddenField,
    IntegerField,
    PasswordField,
    SelectField,
    StringField,
    SubmitField,
    TextAreaField,
)
from wtforms.validators import DataRequired, Email, EqualTo, Length, NumberRange, Optional, Regexp


class LoginForm(FlaskForm):
    username = StringField("Nom d’utilisateur", validators=[DataRequired(), Length(min=3, max=80)])
    password = PasswordField("Mot de passe", validators=[DataRequired(), Length(min=4, max=128)])
    remember = BooleanField("Se souvenir de moi")
    submit = SubmitField("Connexion")


class AutomationRuleForm(FlaskForm):
    name = StringField("Nom", validators=[DataRequired(), Length(max=120)])
    sensor_type = SelectField("Capteur", validators=[DataRequired()])
    sensor_id = SelectField("Identifiant capteur", validators=[Optional()])
    sensor_metric = SelectField("Mesure", validators=[DataRequired()])
    operator = SelectField(
        "Condition",
        choices=[(">", ">"), (">=", "≥"), ("<", "<"), ("<=", "≤"), ("==", "="), ("!=", "≠")],
        validators=[DataRequired()],
    )
    threshold = DecimalField("Seuil", places=2, validators=[DataRequired()], default=0)
    relay_channel = SelectField("Relais à commander", coerce=int, validators=[Optional()])
    relay_action = SelectField(
        "Action",
        choices=[("on", "Allumer"), ("off", "Éteindre"), ("toggle", "Basculer")],
        validators=[Optional()],
    )
    relay_action_enabled = BooleanField("Activer la commande relais", default=True)
    notify_user_id = SelectField(
        "Notifier par email",
        coerce=int,
        validators=[Optional()],
        default=0,
    )
    trigger = HiddenField()
    action = HiddenField()
    cooldown_seconds = IntegerField(
        "Délai entre mesures (s)",
        validators=[Optional(), NumberRange(min=0, max=86400)],
        default=300,
    )
    enabled = BooleanField("Activer la règle", default=True)
    submit = SubmitField("Enregistrer la règle")


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


class SettingForm(FlaskForm):
    key = StringField("Clé", validators=[DataRequired(), Length(max=120)])
    value = StringField("Valeur", validators=[Optional(), Length(max=255)])
    submit = SubmitField("Mettre à jour")


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
