"""Test fixtures and helpers."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

# Ensure project root is on sys.path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Use a throwaway DB before importing the app
_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tmp.close()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp.name}"
os.environ["JWT_SECRET"] = "test-secret-please-use-at-least-32-bytes"
os.environ["LLM_PROVIDER"] = "stub"

import pytest
from fastapi.testclient import TestClient

from flowforge.api.main import create_app
from flowforge.core.database import get_session_factory, init_db
from flowforge.core.security import hash_password
from flowforge.models.user import User


@pytest.fixture(scope="session")
def app():
    return create_app()


@pytest.fixture(scope="session")
def client(app):
    with TestClient(app) as c:
        init_db()
        factory = get_session_factory()
        session = factory()
        try:
            user = session.query(User).filter(User.email == "tester@flowforge.example").first()
            if not user:
                user = User(
                    email="tester@flowforge.example",
                    full_name="Tester",
                    role="admin",
                    hashed_password=hash_password("flowforge-test"),
                )
                session.add(user)
                session.commit()
        finally:
            session.close()
        yield c


@pytest.fixture(scope="session")
def token(client):
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": "tester@flowforge.example", "password": "flowforge-test"},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


@pytest.fixture
def auth_headers(token):
    return {"Authorization": f"Bearer {token}"}
