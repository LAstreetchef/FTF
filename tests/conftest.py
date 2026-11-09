import os
import tempfile

_db_fd, _db_path = tempfile.mkstemp(prefix="ftf-test-", suffix=".db")
os.close(_db_fd)

os.environ["APP_ENV"] = "testing"
os.environ["FLASK_ENV"] = "testing"
os.environ["DATABASE_URL"] = "sqlite:///" + _db_path
os.environ["SESSION_SECRET"] = "test-session-secret"
os.environ["STRIPE_TEST_MODE"] = "true"
os.environ["STRIPE_SECRET_KEY"] = "sk_test_smoke"
os.environ["STRIPE_PUBLISHABLE_KEY"] = "pk_test_smoke"
os.environ["ADMIN_EMAIL"] = "admin@example.com"
os.environ["ADMIN_PASSWORD"] = "admin-password-123"
os.environ["SEED_DEMO_DATA"] = "false"
os.environ["RESTORE_EVENT_BACKUP"] = "false"
os.environ["MAIL_SUPPRESS_SEND"] = "true"
os.environ["IFRAME_EMBED"] = "false"

from app import app, db  # noqa: E402


app.config.update(TESTING=True, PROPAGATE_EXCEPTIONS=True)


import pytest  # noqa: E402
from werkzeug.security import generate_password_hash  # noqa: E402

from models import Admin  # noqa: E402


@pytest.fixture(autouse=True)
def reset_database():
    with app.app_context():
        db.session.remove()
        db.drop_all()
        db.create_all()
        db.session.add(Admin(
            username=os.environ["ADMIN_EMAIL"],
            password_hash=generate_password_hash(os.environ["ADMIN_PASSWORD"]),
        ))
        db.session.commit()
    yield
    with app.app_context():
        db.session.remove()


@pytest.fixture
def client():
    return app.test_client()
