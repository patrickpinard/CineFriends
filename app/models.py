from __future__ import annotations

from datetime import datetime

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from . import db, login_manager


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=True)
    role = db.Column(db.String(20), default="user")
    password_hash = db.Column(db.String(255), nullable=False)
    active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime, nullable=True)
    avatar_filename = db.Column(db.String(255), nullable=True)
    twofa_enabled = db.Column(db.Boolean, default=False)
    twofa_code_hash = db.Column(db.String(255), nullable=True)
    twofa_code_sent_at = db.Column(db.DateTime, nullable=True)
    twofa_trusted_token_hash = db.Column(db.String(255), nullable=True)
    twofa_trusted_created_at = db.Column(db.DateTime, nullable=True)

    automation_rules = db.relationship("AutomationRule", backref="owner", lazy=True)

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    def is_active(self) -> bool:  # type: ignore[override]
        return self.active


@login_manager.user_loader
def load_user(user_id: str) -> User | None:
    return User.query.get(int(user_id))


class AutomationRule(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    trigger = db.Column(db.String(255), nullable=False)
    action = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    enabled = db.Column(db.Boolean, default=True)
    cooldown_seconds = db.Column(db.Integer, default=300)
    last_triggered_at = db.Column(db.DateTime, nullable=True)

    owner_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)


class JournalEntry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    level = db.Column(db.String(20), default="info")
    message = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    details = db.Column(db.JSON, nullable=True)


class Setting(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(120), unique=True, nullable=False)
    value = db.Column(db.String(255), nullable=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class SensorReading(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sensor_type = db.Column(db.String(50), nullable=False)
    sensor_id = db.Column(db.String(120), nullable=True)
    metric = db.Column(db.String(50), nullable=False)
    value = db.Column(db.Float, nullable=True)
    unit = db.Column(db.String(20), nullable=True)
    extra = db.Column(db.JSON, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)


class RelayState(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    channel = db.Column(db.Integer, nullable=False, index=True)
    state = db.Column(db.String(8), nullable=False)
    source = db.Column(db.String(120), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)


class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    audience = db.Column(db.String(50), default="user")  # user, admin, global
    level = db.Column(db.String(20), default="info")
    title = db.Column(db.String(150), nullable=False)
    message = db.Column(db.Text, nullable=False)
    action_url = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    read = db.Column(db.Boolean, default=False)
    persistent = db.Column(db.Boolean, default=False)

    user = db.relationship("User", backref=db.backref("notifications", lazy=True))
