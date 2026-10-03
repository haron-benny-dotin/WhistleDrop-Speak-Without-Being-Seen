import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from whistledrop import store  # noqa: E402
from whistledrop.config import Settings  # noqa: E402
from whistledrop.db import connect  # noqa: E402
from whistledrop.main import create_app  # noqa: E402

MOD_USER = "mod_alice"
MOD_PASS = "correct-horse-battery"


@pytest.fixture
def settings(tmp_path):
    return Settings(database_path=str(tmp_path / "test.db"),
                    case_code_secret=b"test-secret", session_ttl_minutes=60)


@pytest.fixture
def client(settings):
    app = create_app(settings)
    conn = connect(settings.database_path)
    store.create_moderator(conn, MOD_USER, MOD_PASS)
    store.create_moderator(conn, "mod_bob", "another-strong-pass")
    conn.close()
    return TestClient(app)


@pytest.fixture
def auth(client):
    res = client.post("/moderator/login", json={"username": MOD_USER, "password": MOD_PASS})
    assert res.status_code == 200
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


@pytest.fixture
def submit(client):
    def _submit(category="security", description="Server room door is propped open every night."):
        res = client.post("/reports", json={"category": category, "description": description})
        assert res.status_code == 201, res.text
        return res.json()["case_code"]
    return _submit
