import os, pathlib, sys
# Ensure app can be imported without real DB — mock psycopg if needed
os.environ.setdefault("FLASK_SECRET", "test-secret-for-ci")
os.environ.setdefault("DATABASE_URL", os.getenv("DATABASE_URL", ""))
# add project root to path
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
import pytest
from app import app as flask_app

@pytest.fixture
def app():
    flask_app.config.update(TESTING=True, SECRET_KEY="test-secret-for-ci")
    yield flask_app

@pytest.fixture
def client(app):
    return app.test_client()

@pytest.fixture
def admin_client(client):
    # login as admin if DB has user, else mock session
    # For unit tests we mock session directly
    with client.session_transaction() as sess:
        sess["uid"] = "test-admin-id"
        sess["username"] = "test_admin"
        sess["rol"] = "admin"
    return client

@pytest.fixture
def portero_client(client):
    with client.session_transaction() as sess:
        sess["uid"] = "test-portero-id"
        sess["username"] = "test_portero"
        sess["rol"] = "portero"
    return client
