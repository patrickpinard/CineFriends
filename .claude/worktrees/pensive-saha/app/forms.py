from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField
from wtforms import (
    BooleanField,
    DateField,
    PasswordField,
    SelectField,
    StringField,
    SubmitField,
    TextAreaField,
)
from wtforms.validators import DataRequired, Email, EqualTo, Length, Optional, Regexp, URL


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
    date_of_birth = DateField("Date de naissance", validators=[Optional()], format='%Y-%m-%d')
    bio = TextAreaField("Biographie", validators=[Optional(), Length(max=500)], render_kw={"rows": 4})
    company = StringField("Entreprise", validators=[Optional(), Length(max=255)])
    job_title = StringField("Poste / Titre professionnel", validators=[Optional(), Length(max=255)])
    website = StringField("Site web", validators=[Optional(), URL(message="URL invalide"), Length(max=255)])
    linkedin = StringField("LinkedIn", validators=[Optional(), URL(message="URL invalide"), Length(max=255)])
    password = PasswordField("Mot de passe", validators=[Optional(), Length(min=4, max=128)])
    confirm_password = PasswordField(
        "Confirmer le mot de passe",
        validators=[Optional(), EqualTo("password", message="Les mots de passe doivent correspondre.")],
    )
    active = BooleanField("Actif", default=True)
    avatar = FileField("Photo de profil", validators=[Optional(), FileAllowed(["jpg", "jpeg", "png", "gif"], "Formats autorisés: jpg, png, gif.")])
    remove_avatar = BooleanField("Supprimer la photo actuelle")
    # Adresse privée
    street = StringField("Rue", validators=[Optional(), Length(max=255)])
    postal_code = StringField("NPA", validators=[Optional(), Length(max=20)])
    city = StringField("Ville", validators=[Optional(), Length(max=255)])
    country = StringField("Pays", validators=[Optional(), Length(max=255)])
    phone = StringField("Téléphone fixe", validators=[Optional(), Length(max=50)])
    phone_mobile = StringField("Téléphone mobile", validators=[Optional(), Length(max=50)])
    # Adresse professionnelle
    email_professional = StringField("Email professionnel", validators=[Optional(), Email(), Length(max=120)])
    street_professional = StringField("Rue", validators=[Optional(), Length(max=255)])
    postal_code_professional = StringField("NPA", validators=[Optional(), Length(max=20)])
    city_professional = StringField("Ville", validators=[Optional(), Length(max=255)])
    country_professional = StringField("Pays", validators=[Optional(), Length(max=255)])
    phone_professional = StringField("Téléphone professionnel", validators=[Optional(), Length(max=50)])
    twofa_enabled = BooleanField("Activer la double authentification (2FA)")
    role = SelectField("Rôle", choices=[("user", "Utilisateur"), ("admin", "Administrateur")], validators=[Optional()])
    submit = SubmitField("Enregistrer")


class ProfileForm(FlaskForm):
    title = SelectField("Civilité", choices=[("", ""), ("Monsieur", "Monsieur"), ("Madame", "Madame")], validators=[Optional()])
    first_name = StringField("Prénom", validators=[Optional(), Length(max=100)])
    last_name = StringField("Nom", validators=[Optional(), Length(max=100)])
    username = StringField("Nom d'utilisateur", validators=[DataRequired(), Length(min=3, max=80)])
    email = StringField("Email", validators=[Optional(), Email(), Length(max=120)])
    date_of_birth = DateField("Date de naissance", validators=[Optional()], format='%Y-%m-%d')
    bio = TextAreaField("Biographie", validators=[Optional(), Length(max=500)], render_kw={"rows": 4})
    company = StringField("Entreprise", validators=[Optional(), Length(max=255)])
    job_title = StringField("Poste / Titre professionnel", validators=[Optional(), Length(max=255)])
    website = StringField("Site web", validators=[Optional(), URL(message="URL invalide"), Length(max=255)])
    linkedin = StringField("LinkedIn", validators=[Optional(), URL(message="URL invalide"), Length(max=255)])
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
    # Adresse privée
    street = StringField("Rue", validators=[Optional(), Length(max=255)])
    postal_code = StringField("NPA", validators=[Optional(), Length(max=20)])
    city = StringField("Ville", validators=[Optional(), Length(max=255)])
    country = StringField("Pays", validators=[Optional(), Length(max=255)])
    phone = StringField("Téléphone fixe", validators=[Optional(), Length(max=50)])
    phone_mobile = StringField("Téléphone mobile", validators=[Optional(), Length(max=50)])
    # Adresse professionnelle
    email_professional = StringField("Email professionnel", validators=[Optional(), Email(), Length(max=120)])
    street_professional = StringField("Rue", validators=[Optional(), Length(max=255)])
    postal_code_professional = StringField("NPA", validators=[Optional(), Length(max=20)])
    city_professional = StringField("Ville", validators=[Optional(), Length(max=255)])
    country_professional = StringField("Pays", validators=[Optional(), Length(max=255)])
    phone_professional = StringField("Téléphone professionnel", validators=[Optional(), Length(max=50)])
    twofa_enabled = BooleanField("Activer la double authentification (2FA)")
    role = SelectField("Rôle", choices=[("user", "Utilisateur"), ("admin", "Administrateur")], validators=[Optional()])
    active = BooleanField("Actif", default=True)
    submit = SubmitField("Enregistrer le profil")


class RegisterForm(FlaskForm):
    username = StringField("Nom d’utilisateur", validators=[DataRequired(), Length(min=3, max=80)])
    email = StringField("Email", validators=[DataRequired(), Email(), Length(max=120)])
    password = PasswordField("MOT DE PASSE", validators=[DataRequired(), Length(min=4, max=128)])
    confirm_password = PasswordField(
        "MOT DE PASSE",
        validators=[DataRequired(), EqualTo("password", message="Les mots de passe doivent correspondre.")],
    )
    submit = SubmitField("Créer mon compte")


class TwoFactorForm(FlaskForm):
    code = StringField(
        "Code de vérification",
        # La longueur dépend de TWOFA_CODE_LENGTH : on la valide côté backend
        validators=[DataRequired(), Regexp(r"^\d+$", message="Code invalide.")],
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


class BroadcastNotificationForm(FlaskForm):
    title = StringField("Titre", validators=[DataRequired(), Length(min=2, max=100)])
    message = TextAreaField(
        "Message",
        validators=[DataRequired(), Length(min=5, max=500)],
        render_kw={"rows": 4},
    )
    submit = SubmitField("Envoyer à tous")
