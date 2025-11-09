from .models import User
from . import db


def ensure_default_admin() -> None:
    if not User.query.filter_by(username="admin").first():
        admin = User(username="admin", role="admin", active=True)
        admin.set_password("admin")
        db.session.add(admin)
        db.session.commit()
